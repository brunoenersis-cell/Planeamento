"""Proteção simples por palavra-passe para a publicação da aplicação."""
from __future__ import annotations

import hmac
import os

import streamlit as st


def require_access() -> None:
    """Pede acesso apenas quando APP_ACCESS_PASSWORD estiver configurada."""
    configured_password = os.getenv("APP_ACCESS_PASSWORD")
    if not configured_password or st.session_state.get("authenticated"):
        return

    st.title("Cronograma SafetyCulture")
    st.info("Introduza a palavra-passe de acesso.")
    with st.form("access"):
        entered_password = st.text_input("Palavra-passe", type="password")
        submitted = st.form_submit_button("Entrar")
    if submitted and hmac.compare_digest(entered_password, configured_password):
        st.session_state["authenticated"] = True
        st.rerun()
    if submitted:
        st.error("Palavra-passe inválida.")
    st.stop()
