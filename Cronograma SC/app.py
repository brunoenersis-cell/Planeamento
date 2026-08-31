"""Interface Streamlit para exportar cronogramas SafetyCulture."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

import streamlit as st
import pandas as pd

from config import get_settings
from data_processor import EXPORT_COLUMNS, filter_occurrences, normalize_occurrences
from export_service import create_csv, create_excel
from safetyculture_client import SafetyCultureClient, SafetyCultureError
from schedule_service import sync_safetyculture_schedules_with_stats
from security import require_access

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)

st.set_page_config(page_title="Cronograma SafetyCulture", layout="wide")
require_access()
st.title("Cronograma SafetyCulture")
st.caption("Versão 0.6 — cronograma por cliente, com origem auditável de cada tarefa.")

# Procura o token e o URL base nos Secrets do Streamlit Cloud
token = st.secrets.get("SAFETYCULTURE_API_TOKEN", "")
base_url = st.secrets.get("SAFETYCULTURE_BASE_URL", "https://api.safetyculture.io")

# Se o token NÃO estiver definido nos Secrets, mostra o painel na barra lateral para introdução manual
if not token:
    with st.sidebar:
        st.header("Ligação")
        token = st.text_input(
            "API Token", 
            type="password", 
            help="Defina o token nos Secrets do Streamlit Cloud."
        )
        base_url = st.text_input("URL base", value=base_url)
        if st.button("Testar conexão", use_container_width=True):
            try:
                result = SafetyCultureClient(get_settings(token, base_url)).test_safetyculture_connection()
                (st.success if result.ok else st.error)(result.message)
            except SafetyCultureError as exc:
                st.error(str(exc))

st.subheader("Período")
today = date.today()
presets = {"Intervalo personalizado": None, "Mês atual": (today.replace(day=1), (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)), "Próximo mês": ((today.replace(day=28) + timedelta(days=4)).replace(day=1), ((today.replace(day=28) + timedelta(days=4)).replace(day=1).replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)), "Próximos 3 meses": (today, today + timedelta(days=90)), "Próximos 6 meses": (today, today + timedelta(days=180)), "Ano atual": (date(today.year, 1, 1), date(today.year, 12, 31))}
preset = st.selectbox("Seleção rápida", list(presets))
default_period = presets[preset] or (today, today + timedelta(days=30))
period = st.date_input("Datas", value=default_period, format="DD/MM/YYYY")

if st.button("Sincronizar ocorrências", type="primary"):
    if not isinstance(period, tuple) or len(period) != 2:
        st.error("Selecione uma data inicial e uma data final.")
    elif period[0] > period[1]:
        st.error("A data inicial tem de ser anterior à data final.")
    else:
        try:
            start = datetime.combine(period[0], time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            end = datetime.combine(period[1], time.max, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
            LOGGER.info("Iniciando sincronização de occurrences")
            with st.spinner("A consultar schedules e ocorrências..."):
                result = sync_safetyculture_schedules_with_stats(SafetyCultureClient(get_settings(token, base_url)), start, end)
                st.session_state["occurrences"] = normalize_occurrences(result.occurrences)
            LOGGER.info("%s linhas API consolidadas em %s ocorrências", result.api_rows, len(result.occurrences))
            synced_frame = st.session_state["occurrences"]
            named = (
                int(synced_frame["Nome do cronograma"].notna().sum())
                if "Nome do cronograma" in synced_frame.columns
                else 0
            )
            st.success(f"{result.api_rows} linhas devolvidas pela API + {result.planned_rows} tarefas futuras planeadas → {len(result.occurrences)} tarefas no cronograma; {named} com nome do cronograma.")
        except SafetyCultureError as exc:
            st.error(str(exc))

frame = st.session_state.get("occurrences")
if frame is not None:
    # Sessões abertas antes de uma atualização podem conter a estrutura antiga.
    # Completar as colunas em falta evita erros e preserva os registos já consultados.
    frame = frame.reindex(columns=EXPORT_COLUMNS)
    st.session_state["occurrences"] = frame
    st.subheader("Ocorrências")
    filter_specs = [("cliente", "Cliente"), ("origem", "Origem"), ("central", "Central"), ("atividade", "Atividade"), ("template", "Template"), ("estado", "Estado")]
    selected_filters = {}
    columns = st.columns(3)
    for index, (key, label) in enumerate(filter_specs):
        options = sorted(frame[label].dropna().astype(str).unique().tolist())
        selected_filters[key] = columns[index % 3].multiselect(label, options)
    filtered = filter_occurrences(frame, selected_filters)
    st.caption(f"{len(filtered)} registos após filtros")
    display_frame = filtered.copy()
    if "Data/hora limite" in display_frame:
        full_dates = pd.to_datetime(display_frame["Data/hora limite"], errors="coerce", utc=True)
        display_frame["Data"] = full_dates.dt.strftime("%m/%Y").fillna(display_frame["Data"])
    primary_columns = [
        "Data", "Cliente", "Origem", "Nome do cronograma", "Atividade", "Central", "Local", "Estado",
        "Template", "Occurrence ID",
    ]
    visible_columns = [column for column in primary_columns if column in display_frame.columns]
    st.dataframe(display_frame[visible_columns], use_container_width=True, hide_index=True)
    left, right = st.columns(2)
    left.download_button("Exportar Excel", create_excel(filtered), "Cronograma_O&M.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    right.download_button("Exportar CSV", create_csv(filtered), "Cronograma_O&M.csv", "text/csv", use_container_width=True)
