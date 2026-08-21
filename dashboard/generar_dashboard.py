#!/usr/bin/env python3
"""Genera el panel HTML de chats de LuzIA a partir del export de Salesforce.

Uso:
    python dashboard/generar_dashboard.py export.xlsx [-s salida.html]

El export trae dos filas de cola (la fila en blanco y la de "Filtros
aplicados") que se descartan por no tener `status`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Nombre del usuario de pruebas: sus conversaciones no cuentan como tráfico real.
USUARIO_PRUEBAS = "CLIENTE EXTERNO EXTERNO"

# Columna del export -> clave corta usada en el JSON que consume el panel.
COLUMNAS = {
    "sf_id": "id",
    "sf_date - Mes": "mes",
    "sf_date - Día": "dia",
    "status": "st",
    "TIPO": "tipo",
    "sf_installation_agent_name": "agente",
    "sf_requested_agent": "req",
    "specific_category": "cat",
    "category_subtype": "sub",
    "general_category": "gc",
    "business_line": "bl",
    "no_resolution_reason": "nrr",
    "sentiment": "sent",
    "sf_ended_by": "end",
    "summary": "res",
}

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def cargar(ruta: Path) -> pd.DataFrame:
    df = pd.read_excel(ruta)
    faltan = [c for c in COLUMNAS if c not in df.columns]
    if faltan:
        sys.exit(f"El export no trae estas columnas: {', '.join(faltan)}")
    df = df[df["status"].notna()].copy()

    # TIPO viene marcado a mano; si falta, se deduce del usuario de pruebas.
    tipo_deducido = df["sf_installation_agent_name"].eq(USUARIO_PRUEBAS)
    df["TIPO"] = df["TIPO"].fillna(pd.Series(
        ["PRUEBA" if x else "REAL" for x in tipo_deducido], index=df.index))

    df = df[list(COLUMNAS)].rename(columns=COLUMNAS)
    df["req"] = pd.to_numeric(df["req"], errors="coerce").fillna(0).astype(int)
    df["dia"] = pd.to_numeric(df["dia"], errors="coerce").fillna(0).astype(int)
    return df


def periodo(df: pd.DataFrame) -> str:
    presentes = [m for m in MESES if m in set(df["mes"].dropna())]
    if not presentes:
        return "sin fechas"
    primero, ultimo = presentes[0], presentes[-1]
    dia_ini = int(df.loc[df["mes"] == primero, "dia"].min())
    dia_fin = int(df.loc[df["mes"] == ultimo, "dia"].max())
    return f"{dia_ini} de {primero} – {dia_fin} de {ultimo}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("export", type=Path, help="Export .xlsx de Salesforce")
    p.add_argument("-s", "--salida", type=Path,
                   default=Path("dashboard/salida/panel_luzia.html"))
    p.add_argument("-p", "--plantilla", type=Path,
                   default=Path(__file__).with_name("plantilla.html"))
    args = p.parse_args()

    df = cargar(args.export)
    registros = json.loads(df.to_json(orient="records", force_ascii=False))

    payload = {
        "periodo": periodo(df),
        "meses": [m for m in MESES if m in set(df["mes"].dropna())],
        "usuarioPruebas": USUARIO_PRUEBAS,
        "filas": registros,
    }
    datos = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    html = args.plantilla.read_text(encoding="utf-8").replace("/*__DATOS__*/", datos)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(html, encoding="utf-8")

    reales = df[df["tipo"] == "REAL"]
    resueltas = (reales["st"] == "RESUELTA").mean() * 100
    print(f"{args.salida}  ·  {len(df)} chats ({len(reales)} reales) · "
          f"{resueltas:.1f}% resueltas · periodo {payload['periodo']}")


if __name__ == "__main__":
    main()
