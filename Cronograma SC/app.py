"""Interface Streamlit para exportar cronogramas SafetyCulture."""
from __future__ import annotations

import logging
import importlib
from datetime import date, datetime, time, timedelta, timezone

import streamlit as st
import pandas as pd
import altair as alt

from config import get_settings
from data_processor import EXPORT_COLUMNS, filter_occurrences, normalize_occurrences
from export_service import create_csv, create_excel
from safetyculture_client import SafetyCultureClient, SafetyCultureError
from schedule_service import sync_safetyculture_schedules_with_stats
from security import require_access
import report_image

# Streamlit pode manter módulos importados em memória durante uma atualização.
# A recarga garante que o motor de JPG acompanha sempre o código mais recente.
importlib.reload(report_image)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
LOGGER = logging.getLogger(__name__)

STATUS_COLORS = {
    "Disponível": "#3B82F6", "Em andamento": "#F59E0B", "Concluído": "#16A34A",
    "Concluído com atraso": "#D97706", "Em atraso": "#DC2626", "Não concluído": "#991B1B",
    "Não executar": "#6B7280", "Agendada": "#8B5CF6", "Sem estado": "#94A3B8",
}
REPORT_LAYOUT_VERSION = "7"


def _status_chart(frame: pd.DataFrame, dimension: str) -> alt.Chart:
    """Gráfico empilhado para comparar estados entre clientes ou locais."""
    grouped = (
        frame.assign(Estado=frame["Estado"].fillna("Sem estado").astype(str))
        .groupby([dimension, "Estado"], dropna=False).size().reset_index(name="Atividades")
    )
    totals = grouped.groupby(dimension)["Atividades"].sum().sort_values(ascending=False)
    shown = totals.head(15).index.tolist()
    grouped = grouped[grouped[dimension].isin(shown)]
    return alt.Chart(grouped).mark_bar().encode(
        x=alt.X(
            "Atividades:Q",
            stack="zero",
            title="Quantidade",
            axis=alt.Axis(tickMinStep=1, format=".0f"),
        ),
        y=alt.Y(f"{dimension}:N", sort=shown, title=None),
        color=alt.Color("Estado:N", scale=alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values())), title="Estado"),
        tooltip=[alt.Tooltip(f"{dimension}:N"), alt.Tooltip("Estado:N"), alt.Tooltip("Atividades:Q")],
    ).properties(height=max(180, len(shown) * 32))

st.set_page_config(page_title="Cronograma SafetyCulture", layout="wide")
require_access()
st.title("Cronograma SafetyCulture")
st.caption("Versão 1.5 — relatório JPG com prazos mensais e nomes completos.")

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
            progress = st.progress(5, text="A preparar a sincronização…")
            with st.status("A sincronizar ocorrências", expanded=True) as sync_status:
                sync_status.write("A ligar ao SafetyCulture…")
                progress.progress(20, text="A consultar ocorrências e cronogramas…")
                result = sync_safetyculture_schedules_with_stats(SafetyCultureClient(get_settings()), start, end)
                progress.progress(75, text="A organizar tarefas e estados…")
                st.session_state["occurrences"] = normalize_occurrences(result.occurrences)
                progress.progress(100, text="Sincronização concluída.")
                sync_status.update(label="Sincronização concluída", state="complete", expanded=False)
            LOGGER.info("%s linhas API consolidadas em %s ocorrências", result.api_rows, len(result.occurrences))
            synced_frame = st.session_state["occurrences"]
            named = (
                int(synced_frame["Nome do cronograma"].notna().sum())
                if "Nome do cronograma" in synced_frame.columns
                else 0
            )
            st.success(f"{result.api_rows} linhas devolvidas pela API + {result.planned_rows} tarefas futuras planeadas → {len(result.occurrences)} tarefas no cronograma; {named} com nome do cronograma.")
            progress.empty()
        except SafetyCultureError as exc:
            st.error(str(exc))

frame = st.session_state.get("occurrences")
if frame is not None:
    # Sessões abertas antes de uma atualização podem conter a estrutura antiga.
    # Completar as colunas em falta evita erros e preserva os registos já consultados.
    frame = frame.reindex(columns=EXPORT_COLUMNS)
    st.session_state["occurrences"] = frame
    st.subheader("Ocorrências")
    filter_specs = [("cliente", "Cliente"), ("local", "Local"), ("atividade", "Atividade"), ("estado", "Estado")]
    selected_filters = {}
    columns = st.columns(3)
    for index, (key, label) in enumerate(filter_specs):
        options = sorted(frame[label].dropna().astype(str).unique().tolist())
        selected_filters[key] = columns[index % 3].multiselect(label, options)
    filtered = filter_occurrences(frame, selected_filters)
    st.caption(f"{len(filtered)} registos após filtros")

    statuses = filtered["Estado"].fillna("").astype(str)
    completed = statuses.isin(["Concluído", "Concluído com atraso"]).sum()
    in_progress = (statuses == "Em andamento").sum()
    available = (statuses == "Disponível").sum()
    delayed = statuses.isin(["Em atraso", "Não concluído"]).sum()
    unmapped = filtered[filtered["Cliente"].fillna("Não mapeado") == "Não mapeado"]
    indicators = st.columns(6)
    indicators[0].metric("Total", len(filtered))
    indicators[1].metric("Concluídas", int(completed))
    indicators[2].metric("Em andamento", int(in_progress))
    indicators[3].metric("Disponíveis", int(available))
    indicators[4].metric("Atenção", int(delayed), help="Atividades em atraso ou não concluídas.")
    indicators[5].metric("Não mapeadas", len(unmapped), help="Registos cujo Local ainda não está associado a um cliente.")

    if not unmapped.empty:
        with st.expander(f"Identificar {len(unmapped)} registos não mapeados", expanded=False):
            unmapped_summary = (
                unmapped.groupby("Local", dropna=False).agg(
                    Atividades=("Atividade", lambda activities: ", ".join(sorted({str(activity) for activity in activities if pd.notna(activity)}))),
                    Registos=("Atividade", "size"),
                ).reset_index()
            )
            unmapped_summary["Local"] = unmapped_summary["Local"].fillna("Local não indicado")
            st.caption("Associe estes locais a um cliente no ficheiro de mapeamento para que deixem de aparecer como “Não mapeado”.")
            st.dataframe(unmapped_summary, use_container_width=True, hide_index=True)

    display_frame = filtered.copy()
    if "Data/hora de início" in display_frame:
        # O mês operacional é o do início. Usa a data limite só quando a API
        # não disponibiliza início, evitando deslocar atividades concluídas.
        operational_dates = display_frame["Data/hora de início"].fillna(display_frame["Data/hora limite"])
        full_dates = pd.to_datetime(operational_dates, errors="coerce", utc=True)
        display_frame["Data"] = full_dates.dt.strftime("%m/%Y").fillna(display_frame["Data"])
    if "Concluído em" in display_frame:
        completion_dates = pd.to_datetime(display_frame["Concluído em"], errors="coerce", utc=True)
        display_frame["Data de conclusão"] = completion_dates.dt.tz_convert("Europe/Lisbon").dt.strftime("%d/%m/%Y %H:%M").fillna("")
    primary_columns = [
        "Data", "Cliente", "Atividade", "Local", "Estado", "Data de conclusão",
    ]
    visible_columns = [column for column in primary_columns if column in display_frame.columns]
    st.dataframe(display_frame[visible_columns], use_container_width=True, hide_index=True)

    st.subheader("Visão por cliente e local")
    client_tab, local_tab = st.tabs(["Por cliente", "Por local"])
    with client_tab:
        st.altair_chart(_status_chart(filtered, "Cliente"), use_container_width=True)
    with local_tab:
        st.altair_chart(_status_chart(filtered, "Local"), use_container_width=True)

    st.subheader("Pré-visualização do relatório por central")
    available_locations = report_image.report_locations(frame)
    if not available_locations:
        st.info("Sincronize ocorrências com data e local para gerar o relatório.")
    else:
        report_col, month_col = st.columns(2)
        selected_report_location = report_col.selectbox("Central", available_locations, key="report_location")
        first_report_month = date(period[0].year, period[0].month, 1)
        report_month_options = [date(first_report_month.year, month, 1) for month in range(first_report_month.month, 13)]
        selected_report_month = month_col.selectbox(
            "Mês de referência",
            report_month_options,
            format_func=lambda item: item.strftime("%m/%Y"),
            key="report_month",
        )
        st.caption("Ao gerar, a aplicação consulta este mês até dezembro apenas para o relatório. A tabela principal não é alterada.")
        # Invalida automaticamente JPGs guardados quando o modelo visual muda.
        report_key = f"{REPORT_LAYOUT_VERSION}|{selected_report_location}|{selected_report_month.isoformat()}"
        if st.button("Gerar relatório JPG", key="generate_report"):
            try:
                report_start = datetime.combine(selected_report_month, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                report_end = datetime(selected_report_month.year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                progress = st.progress(10, text="A consultar dados do relatório até dezembro…")
                with st.status("A gerar relatório", expanded=True) as report_status:
                    report_status.write("A consultar ocorrências e planeamento da central…")
                    report_sync = sync_safetyculture_schedules_with_stats(
                        SafetyCultureClient(get_settings()), report_start, report_end
                    )
                    progress.progress(70, text="A criar o anexo JPG…")
                    report_frame = normalize_occurrences(report_sync.occurrences)
                    st.session_state["report_jpg"] = report_image.create_central_report_jpg(
                        report_frame, selected_report_location, selected_report_month
                    )
                    st.session_state["report_key"] = report_key
                    report_status.update(label="Relatório pronto para descarregar", state="complete", expanded=False)
                    progress.progress(100, text="Relatório concluído.")
                progress.empty()
            except SafetyCultureError as exc:
                st.error(str(exc))

        if st.session_state.get("report_key") == report_key and st.session_state.get("report_jpg"):
            report_jpg = st.session_state["report_jpg"]
            st.success("Relatório pronto.")
            st.download_button(
                "Descarregar relatório JPG",
                report_jpg,
                file_name=f"Relatorio_{selected_report_location}_{selected_report_month.strftime('%Y_%m')}.jpg",
                mime="image/jpeg",
            )
            with st.expander("Ver miniatura do relatório"):
                st.image(report_jpg, caption=f"{selected_report_location} — {selected_report_month.strftime('%m/%Y')}", width=480)

    left, right = st.columns(2)
    left.download_button("Exportar Excel", create_excel(filtered), "Cronograma_O&M.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    right.download_button("Exportar CSV", create_csv(filtered), "Cronograma_O&M.csv", "text/csv", use_container_width=True)
