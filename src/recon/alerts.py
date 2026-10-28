"""Notifications automatiques : un e-mail HTML par opérateur ayant des avoirs
non conformes + un récapitulatif pour le service facturation.

Par défaut (dry-run) les e-mails sont écrits en fichiers HTML dans
`outputs/alerts/`. Avec `--send`, ils partent via SMTP (variables
d'environnement SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_DOMAIN).
En production, la même logique se branche sur l'API Gmail.
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
LIBELLES = {
    "KO_MOTIF_MANQUANT": "Motif d'avoir non renseigné",
    "KO_AVOIR_SUPERIEUR_FACTURE": "Montant de l'avoir supérieur à la facture",
    "KO_AVOIR_ORPHELIN": "Facture de référence introuvable",
}


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))


def build_alerts(credit_checks: pd.DataFrame, run_date: str) -> dict[str, str]:
    """Retourne {destinataire: html}."""
    env = _env()
    ko = credit_checks[credit_checks["statut"] != "OK"].copy()
    ko["libelle"] = ko["statut"].map(LIBELLES)
    mails: dict[str, str] = {}
    tpl = env.get_template("alert_operator.html.j2")
    for op, grp in ko.groupby("operator"):
        mails[op] = tpl.render(operator=op, run_date=run_date,
                               rows=grp.sort_values("created_at").to_dict("records"))
    recap = (ko.groupby(["operator", "libelle"]).size().unstack(fill_value=0))
    recap["Total"] = recap.sum(axis=1)
    recap = recap.sort_values("Total", ascending=False)
    mails["SERVICE_FACTURATION"] = env.get_template("alert_recap.html.j2").render(
        run_date=run_date, n_total=len(ko), n_ops=ko["operator"].nunique(),
        n_avoirs=len(credit_checks), columns=list(recap.columns),
        rows=[(idx, list(r)) for idx, r in recap.iterrows()])
    return mails


def write_alerts(mails: dict[str, str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for to, html in mails.items():
        (out_dir / f"{to}.html").write_text(html, encoding="utf-8")


def send_alerts(mails: dict[str, str]) -> int:  # pragma: no cover - dépend d'un serveur SMTP
    host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587))
    user, pwd = os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]
    domain = os.environ.get("ALERT_DOMAIN", "example.com")
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pwd)
        for to, html in mails.items():
            msg = MIMEText(html, "html", "utf-8")
            msg["Subject"] = "[Contrôle avoirs] Avoirs à corriger"
            msg["From"], msg["To"] = user, f"{to.lower()}@{domain}"
            s.send_message(msg)
    return len(mails)
