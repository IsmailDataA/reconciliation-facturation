"""Point d'entrée : génère les données, contrôle, rapproche, alerte et publie le rapport.

Usage :
    python run_pipeline.py                 # exécution complète (dry-run des e-mails)
    python run_pipeline.py --orders 200000 # volume plus important
    python run_pipeline.py --send          # envoi réel des alertes (SMTP)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from recon import alerts, charts  # noqa: E402
from recon.evaluate import detected_anomalies, score  # noqa: E402
from recon.generate_data import generate  # noqa: E402
from recon.quality import RULES, run_quality_checks  # noqa: E402
from recon.reconcile import load, run_reconciliation  # noqa: E402

REPO_URL = "https://github.com/ismaildataa/reconciliation-facturation"


def fmt_eur(x: float) -> str:
    return f"{x:,.0f} €".replace(",", " ")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--orders", type=int, default=50_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--send", action="store_true", help="envoyer réellement les alertes")
    args = ap.parse_args()
    t0 = time.perf_counter()

    out, docs = ROOT / "outputs", ROOT / "docs"
    (docs / "img").mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=True)

    print("1/6  Génération des données synthétiques…")
    ds = generate(n_orders=args.orders, seed=args.seed)
    tables = {"orders": ds.orders, "invoices": ds.invoices, "credit_notes": ds.credit_notes}

    print("2/6  Contrôles qualité…")
    q_summary, q_detail = run_quality_checks(tables)

    print("3/6  Rapprochement SQL…")
    conn = sqlite3.connect(out / "facturation.db")
    load(conn, tables)
    res = run_reconciliation(conn)
    conn.close()

    print("4/6  Mesure de la détection…")
    detected = detected_anomalies(res, q_detail)
    scores = score(ds.truth, detected)
    tp, inj, det = scores["vrais_positifs"].sum(), scores["injectees"].sum(), scores["detectees"].sum()

    print("5/6  Alertes opérateurs…")
    run_date = date.today().strftime("%d/%m/%Y")
    mails = alerts.build_alerts(res["credit_checks"], run_date)
    alerts.write_alerts(mails, out / "alerts")
    ex = docs / "exemples"
    ex.mkdir(exist_ok=True)
    worst = res["credit_checks"].query("statut != 'OK'")["operator"].value_counts().index[0]
    (ex / "alerte_operateur.html").write_text(mails[worst], encoding="utf-8")
    (ex / "recap_facturation.html").write_text(mails["SERVICE_FACTURATION"], encoding="utf-8")
    if args.send:
        alerts.send_alerts(mails)

    print("6/6  Rapport & exports…")
    rec, kpi, cn = res["reconciliation"], res["kpi_daily"], res["credit_checks"]
    with pd.ExcelWriter(out / "anomalies_a_traiter.xlsx") as xw:
        rec[rec["statut"] != "OK"].to_excel(xw, sheet_name="Rapprochement", index=False)
        cn[cn["statut"] != "OK"].to_excel(xw, sheet_name="Avoirs", index=False)
        res["date_checks"].to_excel(xw, sheet_name="Dates", index=False)
        q_detail.to_excel(xw, sheet_name="Qualité", index=False)
        kpi.to_excel(xw, sheet_name="KPI quotidiens", index=False)

    charts.daily_ko_rate(kpi, docs / "img" / "taux_ko_quotidien.png")
    charts.anomalies_by_type(scores, docs / "img" / "anomalies_par_type.png")
    charts.operators(cn, docs / "img" / "avoirs_par_operateur.png")
    charts.amount_by_bu(kpi, docs / "img" / "montant_par_bu.png")

    orders_only = rec[rec["statut"] != "KO_ORPHELINE"]
    duree = time.perf_counter() - t0
    k = {
        "taux_ok": f"{100 * (orders_only['statut'] == 'OK').mean():.2f}".replace(".", ","),
        "n_anomalies": f"{len(detected):,}".replace(",", " "),
        "montant": fmt_eur(kpi["montant_a_risque"].sum()),
        "rappel": f"{100 * tp / inj:.1f}".replace(".", ","),
        "precision": f"{100 * tp / det:.1f}".replace(".", ","),
        "duree": f"{duree:.0f}",
        "n_cn": f"{len(cn):,}".replace(",", " "),
        "n_cn_ko": int((cn["statut"] != "OK").sum()),
        "n_rounding": int(args.orders * 0.012 / 4),
    }
    env = Environment(loader=FileSystemLoader(ROOT / "templates"))
    period = f"{ds.orders['order_date'].min():%d/%m/%Y} – {ds.orders['order_date'].max():%d/%m/%Y}"
    html = env.get_template("report.html.j2").render(
        run_date=run_date, n_orders=args.orders, period=period, repo_url=REPO_URL, kpi=k,
        n_rules=len(RULES) + 4, scores=scores.to_dict("records"),
        quality=q_summary.to_dict("records"))
    (docs / "index.html").write_text(html, encoding="utf-8")
    scores.to_csv(out / "score_detection.csv", index=False)

    print(f"\nTerminé en {duree:.1f} s — rappel {k['rappel']} %, précision {k['precision']} %")
    print(f"Rapport : {docs / 'index.html'}  |  Alertes : {len(mails)} e-mails dans {out / 'alerts'}")


if __name__ == "__main__":
    main()
