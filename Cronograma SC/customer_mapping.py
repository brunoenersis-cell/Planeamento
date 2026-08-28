"""Classificação de locais por cliente, mantida num CSV editável."""
from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def load_customer_mapping() -> dict[str, str]:
    """Carrega o mapeamento e inclui equivalências usadas pelo SafetyCulture."""
    path = Path(__file__).with_name("customer_mapping.csv")
    with path.open(encoding="utf-8-sig", newline="") as file:
        mapping = {
            normalize_name(row["Local"]): row["Cliente"].strip()
            for row in csv.DictReader(file)
            if row.get("Local") and row.get("Cliente")
        }
    aliases = {
        "reflexos": "reflexospurpura",
        "arrotas10mw": "arrotas10mw",
        "arrotas1mw": "arrotas1mw",
        "casteloiif": "casteloif",
        "casteloiicv": "castelocv",
        "sadoeparreirinhas": "sado",
        "bustos1": "bustos",
        "senhoradagraca": "senhoradagraca",
    }
    for api_name, csv_name in aliases.items():
        if csv_name in mapping:
            mapping[api_name] = mapping[csv_name]
    return mapping

