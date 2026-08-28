"""Cliente HTTP isolado para a API SafetyCulture."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests

from config import Settings

LOGGER = logging.getLogger(__name__)
OCCURRENCES_PATH = "/scheduling/v1/feed/schedule_occurrences"
SCHEDULES_PATH = "/scheduling/v1/feed/schedules"
SITES_PATH = "/feed/sites"


class SafetyCultureError(Exception):
    """Erro seguro, pronto para mostrar ao utilizador sem dados sensíveis."""


class AuthenticationError(SafetyCultureError):
    pass


class PermissionError(SafetyCultureError):
    pass


class EndpointUnavailableError(SafetyCultureError):
    pass


class NetworkError(SafetyCultureError):
    pass


@dataclass
class ConnectionResult:
    ok: bool
    message: str


class SafetyCultureClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None, timeout: int = 30):
        if not settings.api_token:
            raise AuthenticationError("Configure um API Token antes de continuar.")
        self.base_url = settings.base_url
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.update({"Authorization": f"Bearer {settings.api_token}", "Accept": "application/json"})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        for attempt in range(4):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.Timeout as exc:
                raise NetworkError("A ligação à API excedeu o tempo limite.") from exc
            except requests.RequestException as exc:
                raise NetworkError("Não foi possível estabelecer ligação à API SafetyCulture.") from exc
            if response.status_code == 429 and attempt < 3:
                wait_seconds = min(2**attempt, 8)
                LOGGER.warning("Limite da API atingido; nova tentativa em %ss", wait_seconds)
                time.sleep(wait_seconds)
                continue
            if response.status_code == 401:
                raise AuthenticationError("Token inválido ou expirado.")
            if response.status_code == 403:
                raise PermissionError("O token não tem permissões para consultar schedules.")
            if response.status_code == 404:
                raise EndpointUnavailableError("Endpoint indisponível. Confirme a URL base e a disponibilidade de Schedules.")
            if response.status_code == 429:
                raise SafetyCultureError("A API continua a limitar pedidos. Tente novamente dentro de momentos.")
            if response.status_code >= 500:
                raise EndpointUnavailableError("O serviço SafetyCulture está temporariamente indisponível.")
            if response.status_code >= 400:
                raise SafetyCultureError(f"Pedido rejeitado pela API (HTTP {response.status_code}).")
            try:
                payload = response.json()
            except ValueError as exc:
                raise SafetyCultureError("A API devolveu uma resposta inesperada.") from exc
            if not isinstance(payload, dict):
                raise SafetyCultureError("A API devolveu uma resposta inesperada.")
            return payload
        raise SafetyCultureError("Falha inesperada ao consultar a API.")

    def test_safetyculture_connection(self) -> ConnectionResult:
        """Valida credenciais com uma consulta mínima, sem registar o token."""
        try:
            self._get(OCCURRENCES_PATH, {"limit": 1})
            return ConnectionResult(True, "Conexão bem-sucedida.")
        except AuthenticationError as exc:
            return ConnectionResult(False, str(exc))
        except PermissionError as exc:
            return ConnectionResult(False, str(exc))
        except EndpointUnavailableError as exc:
            return ConnectionResult(False, str(exc))
        except NetworkError as exc:
            return ConnectionResult(False, str(exc))
        except SafetyCultureError as exc:
            return ConnectionResult(False, f"Erro inesperado: {exc}")

    def fetch_all_pages(self, start_date: str, end_date: str, template_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Obtém todas as páginas do feed de ocorrências."""
        params: dict[str, Any] = {"start_date": start_date, "end_date": end_date, "limit": 1000}
        templates = [template for template in (template_ids or []) if template]
        if templates:
            params["template"] = templates
        records: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            page_params = dict(params)
            if token:
                page_params["next_page_token"] = token
            payload = self._get(OCCURRENCES_PATH, page_params)
            page_records = payload.get("schedule_occurrences", payload.get("data", []))
            if not isinstance(page_records, list):
                raise SafetyCultureError("Formato inesperado na paginação de ocorrências.")
            records.extend(item for item in page_records if isinstance(item, dict))
            metadata = payload.get("metadata", {})
            token = metadata.get("next_page_token") if isinstance(metadata, dict) else None
            if not token:
                break
        return records

    def fetch_all_schedules(self, template_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Obtém todos os cronogramas para associar o título às ocorrências."""
        params: dict[str, Any] = {
            "limit": 1000,
            "show_active": "true",
            "show_finished": "true",
            "show_paused": "true",
        }
        templates = [template for template in (template_ids or []) if template]
        if templates:
            params["template"] = templates
        records: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            page_params = dict(params)
            if token:
                page_params["next_page_token"] = token
            payload = self._get(SCHEDULES_PATH, page_params)
            page_records = payload.get("schedules", payload.get("data", []))
            if not isinstance(page_records, list):
                raise SafetyCultureError("Formato inesperado na paginação de cronogramas.")
            records.extend(item for item in page_records if isinstance(item, dict))
            metadata = payload.get("metadata", {})
            token = metadata.get("next_page_token") if isinstance(metadata, dict) else None
            if not token:
                break
        return records

    def fetch_all_sites(self) -> list[dict[str, Any]]:
        """Obtém os locais da organização para traduzir IDs em nomes legíveis."""
        records: list[dict[str, Any]] = []
        offset = 0
        limit = 500
        while True:
            payload = self._get(SITES_PATH, {"limit": limit, "offset": offset})
            page_records = payload.get("sites", payload.get("data", []))
            if not isinstance(page_records, list):
                raise SafetyCultureError("Formato inesperado na paginação de locais.")
            records.extend(item for item in page_records if isinstance(item, dict))
            if len(page_records) < limit:
                break
            offset += limit
        return records
