"""Graphiques du rapport (matplotlib, palette validée daltonisme)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import pandas as pd  # noqa: E402

LABELS = {
    "FACTURE_MANQUANTE": "Facture manquante", "ECART_MONTANT": "Écart de montant",
    "DOUBLON_FACTURE": "Facture en doublon", "FACTURE_ORPHELINE": "Facture sans commande",
    "TVA_INCOHERENTE": "TVA incohérente", "DATE_INCOHERENTE": "Facture avant commande",
    "BU_MANQUANTE": "Business Unit manquante", "MOTIF_MANQUANT": "Avoir sans motif",
    "AVOIR_SUPERIEUR_FACTURE": "Avoir > facture", "AVOIR_ORPHELIN": "Avoir sans facture",
}

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
CRITICAL = "#d03b3b"
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def _style(ax, title: str, subtitle: str | None = None) -> None:
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold", color=INK, pad=22 if subtitle else 10)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9.5, color=INK2)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _save(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=160, facecolor="#fcfcfb")
    plt.close(fig)


def daily_ko_rate(kpi: pd.DataFrame, path: Path) -> None:
    d = kpi.groupby("order_date")[["nb_commandes", "nb_ko"]].sum()
    d.index = pd.to_datetime(d.index)
    rate = 100 * d["nb_ko"] / d["nb_commandes"]
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.plot(rate.index, rate.values, color=BLUE, linewidth=2)
    ax.plot(rate.index, rate.rolling(7, min_periods=1).mean(), color=ORANGE, linewidth=2)
    ax.text(rate.index[-1], rate.rolling(7).mean().iloc[-1], "  moyenne 7 j", color=INK2, fontsize=9, va="center")
    ax.set_ylabel("% de commandes en anomalie", color=INK2, fontsize=9)
    _style(ax, "Taux de commandes en anomalie par jour", "Brut (bleu) et moyenne glissante 7 jours (orange)")
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    _save(fig, path)


def anomalies_by_type(scores: pd.DataFrame, path: Path) -> None:
    s = scores.sort_values("detectees")
    fig, ax = plt.subplots(figsize=(9, 3.8))
    bars = ax.barh(s["anomaly_type"].map(LABELS), s["detectees"],
                   color=BLUE, height=0.62)
    ax.bar_label(bars, padding=4, color=INK2, fontsize=9)
    _style(ax, "Anomalies détectées par type", "Sur 92 jours de données")
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", colors=INK2)
    _save(fig, path)


def operators(credit_checks: pd.DataFrame, path: Path) -> None:
    g = credit_checks.groupby("operator").agg(n=("statut", "size"),
                                              ko=("statut", lambda s: (s != "OK").sum()))
    g["taux"] = 100 * g["ko"] / g["n"]
    mean = 100 * g["ko"].sum() / g["n"].sum()
    g = g.sort_values("taux", ascending=False).head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    colors = [CRITICAL if t > 2 * mean else BLUE for t in g["taux"]]
    bars = ax.barh(g.index, g["taux"], color=colors, height=0.62)
    ax.bar_label(bars, labels=[f"{t:.1f} %" for t in g["taux"]], padding=4, color=INK2, fontsize=9)
    _style(ax, "Taux d'avoirs non conformes par opérateur (top 12)",
           f"En rouge : plus de 2× la moyenne ({mean:.1f} %) — opérateurs à accompagner en priorité")
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", colors=INK2)
    _save(fig, path)


def amount_by_bu(kpi: pd.DataFrame, path: Path) -> None:
    g = kpi.groupby("business_unit")["montant_a_risque"].sum()
    g = g[g > 0].sort_values()
    fig, ax = plt.subplots(figsize=(9, 3.6))
    bars = ax.barh(g.index, g.values, color=BLUE, height=0.62)
    ax.bar_label(bars, labels=[f"{v:,.0f} €".replace(",", " ") for v in g.values],
                 padding=4, color=INK2, fontsize=9)
    _style(ax, "Montant à risque par Business Unit", "Somme des écarts sur les commandes en anomalie")
    ax.grid(axis="x", color=GRID)
    ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", colors=INK2)
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:,.0f} €".replace(",", " "))
    _save(fig, path)
