"""Lógica de consulta e deduplicação de schedules."""
from __future__ import annotations

from typing import Any
from dataclasses import dataclass
from datetime import datetime, timezone

from dateutil.rrule import rrulestr

from safetyculture_client import SafetyCultureClient


@dataclass(frozen=True)
class SyncResult:
    occurrences: list[dict[str, Any]]
    api_rows: int
    planned_rows: int


def _schedule_feed_id(schedule_id: object) -> str:
    """Normaliza o prefixo usado pelo feed de ocorrências para o do feed de schedules.

    A API devolve ``schedule_<uuid>`` nas ocorrências e ``scheduleitem_<uuid>``
    no feed de cronogramas. A equivalência foi validada com a resposta real.
    """
    value = str(schedule_id or "")
    return f"scheduleitem_{value.removeprefix('schedule_')}" if value.startswith("schedule_") else value


def _occurrence_feed_id(schedule_id: object) -> str:
    """Converte ``scheduleitem_`` do feed de cronogramas para ``schedule_``."""
    value = str(schedule_id or "")
    return f"schedule_{value.removeprefix('scheduleitem_')}" if value.startswith("scheduleitem_") else value


def _forecast_occurrences(schedules: list[dict[str, Any]], records: list[dict[str, Any]], start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Calcula tarefas futuras ainda não materializadas no feed de ocorrências.

    SafetyCulture pode não criar uma ocorrência futura com antecedência. A
    previsão usa a regra RRULE devolvida pelo próprio cronograma e fica marcada
    como ``PLANEADA`` para a distinguir de uma ocorrência já devolvida pela API.
    """
    try:
        start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    except ValueError:
        return []
    existing = {
        (str(record.get("schedule_id")), str(record.get("due_time", ""))[:10])
        for record in records
        if record.get("schedule_id") and record.get("due_time")
    }
    forecasts: list[dict[str, Any]] = []
    for schedule in schedules:
        if schedule.get("status") != "ACTIVE" or not schedule.get("recurrence"):
            continue
        try:
            rule = rrulestr(str(schedule["recurrence"]))
            rule_timezone = getattr(rule, "_dtstart", start).tzinfo
            window_start = start.astimezone(rule_timezone) if rule_timezone else start.replace(tzinfo=None)
            window_end = end.astimezone(rule_timezone) if rule_timezone else end.replace(tzinfo=None)
            dates = rule.between(window_start, window_end, inc=True)
        except (TypeError, ValueError):
            continue
        schedule_id = _occurrence_feed_id(schedule.get("id"))
        for due_time in dates:
            due_utc = (
                due_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                if due_time.tzinfo
                else due_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            )
            if (schedule_id, due_utc[:10]) in existing:
                continue
            forecasts.append({
                "id": f"planned_{schedule_id}_{due_utc}",
                "schedule_id": schedule_id,
                "occurrence_id": f"planned_{due_utc}",
                "template_id": schedule.get("template_id"),
                "start_time": due_utc,
                "due_time": due_utc,
                "occurrence_status": "PLANEADA",
                "planned_from_schedule": True,
            })
    return forecasts


def sync_safetyculture_schedules_with_stats(client: SafetyCultureClient, start_date: str, end_date: str, template_ids: list[str] | None = None) -> SyncResult:
    """Consulta ocorrências e consolida uma linha operacional por ocorrência.

    A API pode devolver a mesma ocorrência várias vezes, uma por responsável.
    Os IDs dos responsáveis são preservados em ``assignee_ids`` para auditoria.
    """
    records = client.fetch_all_pages(start_date, end_date, template_ids)
    schedules = client.fetch_all_schedules(template_ids)
    forecasts = _forecast_occurrences(schedules, records, start_date, end_date)
    all_records = [*records, *forecasts]
    sites = client.fetch_all_sites()
    site_names = {
        str(site["id"]): site["name"]
        for site in sites
        if site.get("id") and site.get("name")
    }
    schedules_by_id = {
        str(schedule["id"]): schedule
        for schedule in schedules
        if schedule.get("id")
    }
    unique: dict[str, dict[str, Any]] = {}
    for record in all_records:
        schedule = schedules_by_id.get(_schedule_feed_id(record.get("schedule_id")))
        if schedule:
            site_ids = [str(site_id) for site_id in schedule.get("site_ids", [])]
            record = {
                **record,
                "schedule_name": schedule.get("title"),
                "schedule_site_ids": site_ids,
                "schedule_site_names": [site_names[site_id] for site_id in site_ids if site_id in site_names],
            }
        schedule_id = str(record.get("schedule_id") or "")
        occurrence_id = str(record.get("occurrence_id") or "")
        key = f"{schedule_id}|{occurrence_id}" if schedule_id and occurrence_id else str(record.get("id"))
        assignee_id = record.get("assignee_id") or record.get("user_id")
        if key not in unique:
            unique[key] = {**record, "assignee_ids": [assignee_id] if assignee_id else []}
        elif assignee_id and assignee_id not in unique[key]["assignee_ids"]:
            unique[key]["assignee_ids"].append(assignee_id)
    return SyncResult(occurrences=list(unique.values()), api_rows=len(records), planned_rows=len(forecasts))


def sync_safetyculture_schedules(client: SafetyCultureClient, start_date: str, end_date: str, template_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Compatibilidade: devolve só as ocorrências consolidadas."""
    return sync_safetyculture_schedules_with_stats(client, start_date, end_date, template_ids).occurrences
