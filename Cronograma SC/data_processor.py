"""Normalização tolerante a alterações do contrato da API."""
from __future__ import annotations

from typing import Any

import pandas as pd

from customer_mapping import load_customer_mapping, normalize_name

EXPORT_COLUMNS = [
    "Data", "Cliente", "Origem", "Central", "UPP", "Nome do cronograma", "Atividade", "Técnico", "Estado", "Schedule ID", "Occurrence ID",
    "Template ID", "Template", "Assignee ID", "Local ID", "Local", "Data/hora de início",
    "Data/hora de fim", "Data/hora limite", "Concluído em", "Frequência", "Criado em", "Atualizado em", "Audit ID",
]


def _first(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _as_text(value: Any) -> Any:
    """Converte listas provenientes da API num valor legível para a tabela."""
    return ", ".join(str(entry) for entry in value) if isinstance(value, (list, tuple, set)) else value


def normalize_occurrences(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    customers = load_customer_mapping()
    for item in records:
        due = _first(item, "due_time", "due_date")
        due_timestamp = pd.to_datetime(due, errors="coerce", utc=True)
        operational_month = due_timestamp.strftime("%m/%Y") if not pd.isna(due_timestamp) else due
        local = _as_text(_first(item, "site_name", "schedule_site_names"))
        local_names = str(local or "").split(", ")
        customer_names = sorted({customers[normalize_name(name)] for name in local_names if normalize_name(name) in customers})
        rows.append({
            "Data": operational_month,
            "Cliente": ", ".join(customer_names) if customer_names else "Não mapeado",
            "Origem": "Recorrência prevista" if item.get("planned_from_schedule") else "API SafetyCulture",
            "Central": _first(item, "central"),
            "UPP": _first(item, "upp"),
            "Nome do cronograma": _first(item, "schedule_name", "schedule_title"),
            "Atividade": _first(item, "activity_name", "schedule_name", "description", "name"),
            "Técnico": _first(item, "assignee_name", "user_name", "assignee"),
            "Estado": _first(item, "occurrence_status", "assignee_status", "status"),
            "Schedule ID": item.get("schedule_id"), "Occurrence ID": item.get("occurrence_id"),
            "Template ID": item.get("template_id"), "Template": _first(item, "template_name"),
            "Assignee ID": _as_text(_first(item, "assignee_ids", "assignee_id", "user_id")),
            "Local ID": _as_text(_first(item, "site_id", "schedule_site_ids")),
            "Local": local,
            "Data/hora de início": item.get("start_time"), "Data/hora de fim": item.get("end_time"),
            "Data/hora limite": due, "Concluído em": item.get("completed_at"), "Frequência": item.get("recurrence"),
            "Criado em": item.get("created_at"), "Atualizado em": _first(item, "updated_at", "modified_at"), "Audit ID": item.get("audit_id"),
        })
    frame = pd.DataFrame(rows, columns=EXPORT_COLUMNS)
    if not frame.empty:
        frame["_sort"] = pd.to_datetime(frame["Data/hora limite"], errors="coerce", utc=True)
        frame = frame.sort_values("_sort", na_position="last").drop(columns="_sort")
    return frame


def filter_occurrences(frame: pd.DataFrame, filters: dict[str, list[str]]) -> pd.DataFrame:
    result = frame.copy()
    field_map = {"cliente": "Cliente", "origem": "Origem", "central": "Central", "upp": "UPP", "atividade": "Atividade", "template": "Template", "tecnico": "Técnico", "estado": "Estado"}
    for filter_name, selected in filters.items():
        column = field_map.get(filter_name)
        if column and selected:
            result = result[result[column].fillna("").isin(selected)]
    return result
