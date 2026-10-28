import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from recon.alerts import build_alerts  # noqa: E402
from recon.evaluate import detected_anomalies, score  # noqa: E402
from recon.generate_data import generate  # noqa: E402
from recon.quality import run_quality_checks  # noqa: E402
from recon.reconcile import load, run_reconciliation  # noqa: E402


@pytest.fixture(scope="module")
def pipeline():
    ds = generate(n_orders=8_000, seed=7)
    tables = {"orders": ds.orders, "invoices": ds.invoices, "credit_notes": ds.credit_notes}
    q_summary, q_detail = run_quality_checks(tables)
    conn = sqlite3.connect(":memory:")
    load(conn, tables)
    res = run_reconciliation(conn)
    return ds, q_summary, q_detail, res


def test_every_order_gets_one_status(pipeline):
    ds, _, _, res = pipeline
    rec = res["reconciliation"]
    orders = rec[rec["statut"] != "KO_ORPHELINE"]
    assert orders["order_id"].is_unique
    assert len(orders) == len(ds.orders)


def test_detection_is_complete_and_precise(pipeline):
    ds, _, q_detail, res = pipeline
    s = score(ds.truth, detected_anomalies(res, q_detail))
    assert (s["rappel_pct"] == 100).all(), s
    assert (s["precision_pct"] == 100).all(), s


def test_rounding_noise_is_tolerated():
    """Un écart d'un centime ne doit jamais être signalé comme anomalie."""
    orders = pd.DataFrame({"order_id": [1, 2], "order_date": ["2026-01-01"] * 2,
                           "business_unit": ["BU-A"] * 2, "channel": ["DRIVE"] * 2,
                           "customer_id": [1, 2], "amount_ttc": [100.00, 50.00]})
    invoices = pd.DataFrame({"invoice_id": ["F1", "F2"], "order_id": [1, 2],
                             "invoice_date": ["2026-01-01"] * 2, "vat_rate": [0.2] * 2,
                             "amount_ht": [83.33, 41.67], "amount_tva": [16.68, 8.33],
                             "amount_ttc": [100.01, 51.00]})
    credit = pd.DataFrame(columns=["credit_id", "invoice_id", "operator", "created_at",
                                   "amount", "reason_code"])
    conn = sqlite3.connect(":memory:")
    load(conn, {"orders": orders, "invoices": invoices, "credit_notes": credit})
    rec = run_reconciliation(conn)["reconciliation"].set_index("order_id")
    assert rec.loc[1, "statut"] == "OK"
    assert rec.loc[2, "statut"] == "KO_MONTANT"


def test_quality_rules_flag_null_business_unit(pipeline):
    ds, q_summary, _, _ = pipeline
    row = q_summary.set_index("rule_id").loc["ORD_BU_NOT_NULL"]
    assert row["n_failed"] == ds.orders["business_unit"].isna().sum() > 0


def test_one_alert_per_operator_plus_recap(pipeline):
    _, _, _, res = pipeline
    cn = res["credit_checks"]
    mails = build_alerts(cn, "01/01/2026")
    n_ops = cn.loc[cn["statut"] != "OK", "operator"].nunique()
    assert len(mails) == n_ops + 1
    assert "SERVICE_FACTURATION" in mails
