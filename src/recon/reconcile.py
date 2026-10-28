"""Exécution des requêtes SQL de rapprochement sur une base SQLite.

SQLite est utilisé pour que le projet tourne partout sans installation ;
les requêtes restent en SQL standard et se portent sur BigQuery / PostgreSQL.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
TOLERANCE_EUR = 0.05  # écart toléré entre commande et facture (arrondis)


def _sql(name: str) -> str:
    return (SQL_DIR / name).read_text(encoding="utf-8")


def load(conn: sqlite3.Connection, tables: dict[str, pd.DataFrame]) -> None:
    for name, df in tables.items():
        out = df.copy()
        for col in out.select_dtypes(include=["datetime64"]).columns:
            out[col] = out[col].dt.strftime("%Y-%m-%d")
        out.to_sql(name, conn, index=False, if_exists="replace")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_inv_order ON invoices(order_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_inv_id ON invoices(invoice_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_ord_id ON orders(order_id)")


def run_reconciliation(conn: sqlite3.Connection,
                       tolerance: float = TOLERANCE_EUR) -> dict[str, pd.DataFrame]:
    recon = pd.read_sql(_sql("01_rapprochement_commandes_factures.sql"), conn,
                        params={"tolerance": tolerance})
    recon.to_sql("reconciliation", conn, index=False, if_exists="replace")
    return {
        "reconciliation": recon,
        "credit_checks": pd.read_sql(_sql("02_controle_avoirs.sql"), conn),
        "kpi_daily": pd.read_sql(_sql("03_kpi_quotidiens.sql"), conn),
        "date_checks": pd.read_sql(_sql("04_coherence_dates.sql"), conn),
    }
