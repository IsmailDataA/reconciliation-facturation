"""Mesure objective de la détection : anomalies détectées vs anomalies injectées."""
from __future__ import annotations

import pandas as pd

# statut / règle détecté -> type d'anomalie injecté
MAPPING = {
    "KO_FACTURE_MANQUANTE": "FACTURE_MANQUANTE",
    "KO_MONTANT": "ECART_MONTANT",
    "KO_DOUBLON": "DOUBLON_FACTURE",
    "KO_ORPHELINE": "FACTURE_ORPHELINE",
    "INV_VAT_CONSISTENT": "TVA_INCOHERENTE",
    "ORD_BU_NOT_NULL": "BU_MANQUANTE",
    "DATE_INCOHERENTE": "DATE_INCOHERENTE",
    "KO_MOTIF_MANQUANT": "MOTIF_MANQUANT",
    "KO_AVOIR_SUPERIEUR_FACTURE": "AVOIR_SUPERIEUR_FACTURE",
    "KO_AVOIR_ORPHELIN": "AVOIR_ORPHELIN",
}


def detected_anomalies(results: dict[str, pd.DataFrame], quality_detail: pd.DataFrame) -> pd.DataFrame:
    rec = results["reconciliation"]
    rows = []
    ko = rec[rec["statut"] != "OK"]
    for _, r in ko.iterrows():
        key = r["invoice_id"] if r["statut"] == "KO_ORPHELINE" else str(r["order_id"])
        rows.append((key, MAPPING[r["statut"]]))
    for _, r in quality_detail[quality_detail["rule_id"].isin(MAPPING)].iterrows():
        rows.append((r["entity_id"], MAPPING[r["rule_id"]]))
    for inv in results["date_checks"]["invoice_id"]:
        rows.append((inv, "DATE_INCOHERENTE"))
    cn = results["credit_checks"]
    for _, r in cn[cn["statut"] != "OK"].iterrows():
        rows.append((r["credit_id"], MAPPING[r["statut"]]))
    return pd.DataFrame(rows, columns=["entity_id", "anomaly_type"]).drop_duplicates()


def score(truth: pd.DataFrame, detected: pd.DataFrame) -> pd.DataFrame:
    t = truth[["entity_id", "anomaly_type"]].assign(injected=1)
    d = detected.assign(detected=1)
    m = t.merge(d, on=["entity_id", "anomaly_type"], how="outer").fillna(0)
    out = m.groupby("anomaly_type").agg(
        injectees=("injected", "sum"), detectees=("detected", "sum"),
        vrais_positifs=("injected", lambda s: int(((s == 1) & (m.loc[s.index, "detected"] == 1)).sum())),
    ).astype(int)
    out["rappel_pct"] = (100 * out["vrais_positifs"] / out["injectees"].where(out["injectees"] > 0)).round(1)
    out["precision_pct"] = (100 * out["vrais_positifs"] / out["detectees"].where(out["detectees"] > 0)).round(1)
    return out.reset_index().sort_values("injectees", ascending=False)
