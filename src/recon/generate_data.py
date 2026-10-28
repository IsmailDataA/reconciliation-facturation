"""Génération d'un jeu de données synthétique et réaliste : commandes e-commerce,
factures et avoirs, avec des anomalies injectées de façon traçable.

Aucune donnée d'entreprise réelle n'est utilisée. Chaque anomalie injectée est
enregistrée dans une table de vérité (`truth`) afin de mesurer objectivement la
capacité du pipeline à la détecter (rappel / précision).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

BUSINESS_UNITS = [
    "BU-PARIS-NORD", "BU-PARIS-SUD", "BU-LYON", "BU-LILLE",
    "BU-MARSEILLE", "BU-BORDEAUX", "BU-NANTES", "BU-TOULOUSE",
]
CHANNELS = ["DRIVE", "LIVRAISON", "MARKETPLACE"]
CHANNEL_WEIGHTS = [0.55, 0.30, 0.15]
VAT_RATES = [0.055, 0.10, 0.20]
VAT_WEIGHTS = [0.60, 0.10, 0.30]
REASON_CODES = ["PRODUIT_MANQUANT", "PRODUIT_ABIME", "RETARD_LIVRAISON",
                "GESTE_COMMERCIAL", "ERREUR_PRIX"]
# Jours de la semaine (lundi=0) : plus de commandes en fin de semaine
WEEKDAY_WEIGHTS = np.array([0.12, 0.12, 0.13, 0.14, 0.17, 0.20, 0.12])


@dataclass
class Dataset:
    orders: pd.DataFrame
    invoices: pd.DataFrame
    credit_notes: pd.DataFrame
    truth: pd.DataFrame  # entity, entity_id, anomaly_type


def _take(pool: list, rng: np.random.Generator, k: int) -> np.ndarray:
    """Tire k éléments sans remise dans `pool` et les retire du pool
    (garantit qu'un enregistrement ne porte qu'une seule anomalie)."""
    idx = rng.choice(len(pool), size=k, replace=False)
    chosen = np.array([pool[i] for i in idx])
    for i in sorted(idx, reverse=True):
        pool.pop(i)
    return chosen


def generate(n_orders: int = 50_000, start: str = "2026-07-01", days: int = 92,
             anomaly_rate: float = 0.012, n_operators: int = 25,
             seed: int = 42) -> Dataset:
    rng = np.random.default_rng(seed)
    truth: list[tuple[str, str, str]] = []

    # ------------------------------------------------------------------ commandes
    calendar = pd.date_range(start, periods=days, freq="D")
    day_w = WEEKDAY_WEIGHTS[calendar.dayofweek]
    day_w = day_w / day_w.sum()
    order_dates = rng.choice(calendar.values, size=n_orders, p=day_w)

    orders = pd.DataFrame({
        "order_id": np.arange(733_000_000, 733_000_000 + n_orders),
        "order_date": pd.to_datetime(order_dates),
        "business_unit": rng.choice(BUSINESS_UNITS, n_orders),
        "channel": rng.choice(CHANNELS, n_orders, p=CHANNEL_WEIGHTS),
        "customer_id": rng.integers(1, 18_000, n_orders),
        "amount_ttc": np.round(rng.lognormal(mean=4.25, sigma=0.55, size=n_orders), 2),
    }).sort_values(["order_date", "order_id"]).reset_index(drop=True)

    # ------------------------------------------------------------------ factures
    vat = rng.choice(VAT_RATES, n_orders, p=VAT_WEIGHTS)
    ht = np.round(orders["amount_ttc"] / (1 + vat), 2)
    invoices = pd.DataFrame({
        "invoice_id": [f"FAC{bu[3:6]}{i:08d}" for i, bu in
                       zip(range(1, n_orders + 1), orders["business_unit"])],
        "order_id": orders["order_id"],
        "invoice_date": orders["order_date"]
        + pd.to_timedelta(rng.integers(0, 3, n_orders), unit="D"),
        "vat_rate": vat,
        "amount_ht": ht,
        "amount_tva": np.round(orders["amount_ttc"] - ht, 2),
        "amount_ttc": orders["amount_ttc"],
    })

    k = max(1, int(n_orders * anomaly_rate / 4))  # volume par type d'anomalie
    pool = list(range(n_orders))  # indices de commandes « vierges »

    # 1. Facture manquante
    missing = _take(pool, rng, k)
    truth += [("order", str(orders.at[i, "order_id"]), "FACTURE_MANQUANTE") for i in missing]

    # 2. Écart de montant (au-delà de la tolérance)
    mismatch = _take(pool, rng, k)
    factor = 1 + rng.choice([-1, 1], k) * rng.uniform(0.03, 0.35, k)
    invoices.loc[mismatch, "amount_ttc"] = np.round(invoices.loc[mismatch, "amount_ttc"] * factor, 2)
    invoices.loc[mismatch, "amount_ht"] = np.round(
        invoices.loc[mismatch, "amount_ttc"] / (1 + invoices.loc[mismatch, "vat_rate"]), 2)
    invoices.loc[mismatch, "amount_tva"] = np.round(
        invoices.loc[mismatch, "amount_ttc"] - invoices.loc[mismatch, "amount_ht"], 2)
    truth += [("order", str(orders.at[i, "order_id"]), "ECART_MONTANT") for i in mismatch]

    # 2bis. Bruit d'arrondi (± 1 centime) : NE DOIT PAS être signalé
    rounding = _take(pool, rng, k)
    invoices.loc[rounding, "amount_ttc"] = np.round(
        invoices.loc[rounding, "amount_ttc"] + rng.choice([-0.01, 0.01], k), 2)
    invoices.loc[rounding, "amount_tva"] = np.round(
        invoices.loc[rounding, "amount_ttc"] - invoices.loc[rounding, "amount_ht"], 2)

    # 3. TVA incohérente (HT + TVA ≠ TTC)
    vat_bad = _take(pool, rng, k)
    invoices.loc[vat_bad, "amount_tva"] = np.round(
        invoices.loc[vat_bad, "amount_tva"] + rng.uniform(0.5, 6, k), 2)
    truth += [("invoice", invoices.at[i, "invoice_id"], "TVA_INCOHERENTE") for i in vat_bad]

    # 4. Facture antérieure à la commande
    date_bad = _take(pool, rng, k // 2)
    invoices.loc[date_bad, "invoice_date"] = orders.loc[date_bad, "order_date"] - pd.to_timedelta(
        rng.integers(2, 20, len(date_bad)), unit="D")
    truth += [("invoice", invoices.at[i, "invoice_id"], "DATE_INCOHERENTE") for i in date_bad]

    # 5. Business Unit non renseignée
    bu_null = _take(pool, rng, k // 2)
    orders.loc[bu_null, "business_unit"] = None
    truth += [("order", str(orders.at[i, "order_id"]), "BU_MANQUANTE") for i in bu_null]

    # 6. Doublons de facture
    dup = _take(pool, rng, k)
    dup_rows = invoices.loc[dup].copy()
    dup_rows["invoice_id"] = [f"{x}D" for x in dup_rows["invoice_id"]]
    truth += [("order", str(orders.at[i, "order_id"]), "DOUBLON_FACTURE") for i in dup]

    # 7. Factures orphelines (commande inexistante)
    clean_ids = set(invoices.loc[pool, "invoice_id"])  # factures sans aucune anomalie
    orphan = invoices.loc[rng.choice(pool, size=k, replace=False)].copy()
    orphan["order_id"] = rng.integers(900_000_000, 999_999_999, k)
    orphan["invoice_id"] = [f"FACORP{i:08d}" for i in range(k)]
    truth += [("invoice", x, "FACTURE_ORPHELINE") for x in orphan["invoice_id"]]

    invoices = invoices.drop(index=missing)
    invoices = pd.concat([invoices, dup_rows, orphan], ignore_index=True)

    # ------------------------------------------------------------------ avoirs
    # Chaque opérateur a son propre taux d'erreur : c'est ce que l'on veut piloter.
    operators = [f"OP{i:03d}" for i in range(1, n_operators + 1)]
    op_error = rng.beta(1.2, 18, n_operators)
    op_error[rng.choice(n_operators, 3, replace=False)] *= 3.5  # 3 opérateurs à accompagner

    clean_inv = invoices[invoices["invoice_id"].isin(clean_ids)]
    n_cn = int(len(clean_inv) * 0.06)
    base = clean_inv.sample(n_cn, random_state=seed + 1).reset_index(drop=True)
    op_idx = rng.integers(0, n_operators, n_cn)
    credit = pd.DataFrame({
        "credit_id": [f"AV{i:07d}" for i in range(1, n_cn + 1)],
        "invoice_id": base["invoice_id"],
        "operator": np.array(operators)[op_idx],
        "created_at": base["invoice_date"] + pd.to_timedelta(rng.integers(1, 15, n_cn), unit="D"),
        "amount": np.round(base["amount_ttc"] * rng.uniform(0.05, 0.6, n_cn), 2),
        "reason_code": rng.choice(REASON_CODES, n_cn),
    })
    is_err = rng.random(n_cn) < op_error[op_idx]
    err_type = rng.choice(["MOTIF_MANQUANT", "AVOIR_SUPERIEUR_FACTURE", "AVOIR_ORPHELIN"],
                          n_cn, p=[0.6, 0.25, 0.15])
    for i in np.where(is_err)[0]:
        t = err_type[i]
        if t == "MOTIF_MANQUANT":
            credit.at[i, "reason_code"] = None
        elif t == "AVOIR_SUPERIEUR_FACTURE":
            credit.at[i, "amount"] = round(base.at[i, "amount_ttc"] * rng.uniform(1.1, 2.0), 2)
        else:
            credit.at[i, "invoice_id"] = f"FACXXX{rng.integers(1e7, 1e8)}"
        truth.append(("credit_note", credit.at[i, "credit_id"], t))

    truth_df = pd.DataFrame(truth, columns=["entity", "entity_id", "anomaly_type"])
    return Dataset(orders=orders, invoices=invoices, credit_notes=credit, truth=truth_df)


if __name__ == "__main__":  # pragma: no cover
    ds = generate()
    print(ds.orders.shape, ds.invoices.shape, ds.credit_notes.shape)
    print(ds.truth["anomaly_type"].value_counts())
