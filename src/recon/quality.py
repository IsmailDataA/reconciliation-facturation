"""Moteur de règles de qualité des données.

Chaque règle est déclarative : une table, un identifiant d'entité, une sévérité
et une fonction qui renvoie le masque des lignes NON conformes. Ajouter une règle
= ajouter une entrée dans `RULES`, sans toucher au reste du pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

TOLERANCE_TVA = 0.02  # € — écart toléré entre HT + TVA et TTC (arrondis)


@dataclass(frozen=True)
class Rule:
    rule_id: str
    table: str
    id_col: str
    severity: str  # BLOQUANT | MAJEUR | MINEUR
    description: str
    check: Callable[[pd.DataFrame], pd.Series]  # True = ligne en anomalie


RULES: list[Rule] = [
    Rule("ORD_PK_UNIQUE", "orders", "order_id", "BLOQUANT",
         "Identifiant de commande unique",
         lambda df: df["order_id"].duplicated(keep=False)),
    Rule("ORD_BU_NOT_NULL", "orders", "order_id", "MAJEUR",
         "Business Unit renseignée",
         lambda df: df["business_unit"].isna() | (df["business_unit"] == "")),
    Rule("ORD_AMOUNT_POSITIVE", "orders", "order_id", "BLOQUANT",
         "Montant de commande strictement positif",
         lambda df: ~(df["amount_ttc"] > 0)),
    Rule("INV_PK_UNIQUE", "invoices", "invoice_id", "BLOQUANT",
         "Numéro de facture unique",
         lambda df: df["invoice_id"].duplicated(keep=False)),
    Rule("INV_VAT_CONSISTENT", "invoices", "invoice_id", "MAJEUR",
         "HT + TVA = TTC (tolérance 2 centimes)",
         lambda df: (df["amount_ht"] + df["amount_tva"] - df["amount_ttc"]).abs() > TOLERANCE_TVA),
    Rule("INV_VAT_RATE_VALID", "invoices", "invoice_id", "MAJEUR",
         "Taux de TVA dans le référentiel (5,5 %, 10 %, 20 %)",
         lambda df: ~df["vat_rate"].round(3).isin([0.055, 0.10, 0.20])),
    Rule("CN_AMOUNT_POSITIVE", "credit_notes", "credit_id", "BLOQUANT",
         "Montant d'avoir strictement positif",
         lambda df: ~(df["amount"] > 0)),
]


def run_quality_checks(tables: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exécute toutes les règles.

    Retourne (synthèse par règle, détail des lignes en anomalie)."""
    summary, details = [], []
    for rule in RULES:
        df = tables[rule.table]
        mask = rule.check(df).fillna(True)
        n_ko = int(mask.sum())
        summary.append({
            "rule_id": rule.rule_id, "table": rule.table, "severity": rule.severity,
            "description": rule.description, "n_checked": len(df), "n_failed": n_ko,
            "pct_failed": round(100 * n_ko / max(len(df), 1), 3),
            "status": "OK" if n_ko == 0 else "KO",
        })
        if n_ko:
            details.append(pd.DataFrame({
                "rule_id": rule.rule_id, "table": rule.table, "severity": rule.severity,
                "entity_id": df.loc[mask, rule.id_col].astype(str).values,
            }))
    detail = pd.concat(details, ignore_index=True) if details else pd.DataFrame(
        columns=["rule_id", "table", "severity", "entity_id"])
    return pd.DataFrame(summary), detail
