"""Gera a figura do README a partir das notas históricas publicadas."""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
with (ROOT / "results" / "historical" / "summary.csv").open(encoding="utf-8", newline="") as stream:
    rows = [row for row in csv.DictReader(stream) if row["method"] != "noRAG"]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
fig, ax = plt.subplots(figsize=(8.4, 4.6), layout="constrained")
labels = {"A": "A (Standard)", "B": "B (Fine grained)", "C": "C (Coarse grained)"}
bars = ax.barh([labels[row["method"]] for row in rows],
               [float(row["Global_Score"]) for row in rows],
               color=["#2563eb", "#0d9488", "#7c3aed"], height=0.55)
ax.bar_label(bars, fmt="%.2f", padding=7)
ax.invert_yaxis()
ax.set_xlim(0, 100)
ax.set_xlabel("Score global médio (0–100)")
ax.set_title("FIA Regulation RAG: resultados históricos", loc="left", weight="bold", pad=18)
ax.set_axisbelow(True)
ax.grid(axis="x", alpha=0.2)
ax.spines[["top", "right", "left"]].set_visible(False)
ax.tick_params(axis="y", length=0)
output = ROOT / "results" / "historical" / "comparison.png"
fig.savefig(output, dpi=180, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(output)
