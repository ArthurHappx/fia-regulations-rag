"""Validação offline das correções metodológicas, sem baixar modelos ou chamar APIs."""

import csv
import json
import math
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import nbformat
from langchain_core.runnables import RunnableLambda

ROOT = Path(__file__).resolve().parents[1]
notebook = nbformat.read(ROOT / "FIA_Regulation_RAG.ipynb", as_version=4)
nbformat.validate(notebook)
cells = notebook.cells
for index, cell in enumerate(cells):
    if cell.cell_type == "code":
        compile(cell.source, f"cell-{index}", "exec")

calls = []


def fake_model(prompt):
    calls.append(prompt.to_string())
    return SimpleNamespace(content="resposta simulada")


def unexpected_translation(query):
    raise AssertionError("Baseline sem RAG não deve chamar DeepL")


scope = {"client": RunnableLambda(fake_model), "deepl_translate": unexpected_translation}
exec(cells[21].source, scope)
exec(cells[23].source, scope)
answer, documents = scope["ask_question"]("pergunta de teste", None)
assert answer == "resposta simulada" and documents == []
assert "No reference documents are supplied" in calls[-1]
assert "ONLY the provided context" not in calls[-1]
scope["generate_answer"]("pergunta de teste", [SimpleNamespace(page_content="evidência de teste")])
assert "ONLY the provided context" in calls[-1] and "evidência de teste" in calls[-1]

exec(cells[30].source, scope)
for value, expected in [(0, 0), (100, 100), (" 75 ", 75), ("75.0", 75)]:
    assert scope["safe_int"](value) == expected
for value in [None, -1, 101, "Nota: 90", "2026", "", float("nan")]:
    assert math.isnan(scope["safe_int"](value))

# Um lote simulado confere a gravação do CSV e de sua configuração sem chamadas externas.
scope.update({"Path": Path, "sys": sys, "PROJECT_ROOT": ROOT,
              "DATA_ACTUAL_REVISION": "offline-check", "NVIDIA_MODEL": "mock-generator",
              "NVIDIA_JUDGE_MODEL": "mock-judge"})
for name in ["cc_judge", "qr_judge", "id_judge", "ac_judge", "ir_judge"]:
    scope[name] = RunnableLambda(lambda _: SimpleNamespace(content="80"))
with tempfile.TemporaryDirectory(prefix="fia-validation-") as temporary:
    temp = Path(temporary)
    questions = temp / "questions.json"
    questions.write_text(json.dumps([
        {"pergunta": "pergunta 1", "resposta_esperada": "referência 1"},
        {"pergunta": "pergunta 2", "resposta_esperada": "referência 2"},
    ]), encoding="utf-8")
    output = temp / "avaliacao.csv"
    result = scope["process_json_questions_range"](
        str(questions), str(output), None, start_idx=2, end_idx=2,
    )
    metadata = json.loads(output.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert len(result) == 1 and result.iloc[0]["Pergunta"] == "pergunta 2"
    assert result.iloc[0]["Answer_Correctness_Score"] == 80
    assert metadata["start_idx"] == metadata["end_idx"] == 2
    assert metadata["retrieval_enabled"] is False
    assert "API_KEY" not in json.dumps(metadata)

with (ROOT / "results/historical/scores.csv").open(encoding="utf-8", newline="") as stream:
    scores = list(csv.DictReader(stream))
with (ROOT / "results/historical/summary.csv").open(encoding="utf-8", newline="") as stream:
    summary = list(csv.DictReader(stream))
weights = json.loads((ROOT / "results/historical/provenance.json").read_text(encoding="utf-8"))["weights"]
assert len(scores) == 400 and len(summary) == 4
for row in scores:
    assert math.isclose(sum(float(row[key]) * weight for key, weight in weights.items()), float(row["Global_Score"]))
for row in summary:
    method_scores = [score for score in scores if score["method"] == row["method"]]
    assert len(method_scores) == int(row["n_questions"]) == 100
    for key in [*weights, "Global_Score"]:
        actual = sum(float(score[key]) for score in method_scores) / len(method_scores)
        assert math.isclose(actual, float(row[key]), abs_tol=0.00051)
diagnostics = json.loads((ROOT / "results/analysis/retrieval_diagnostics.json").read_text(encoding="utf-8"))
provenance = json.loads((ROOT / "results/historical/provenance.json").read_text(encoding="utf-8"))
for source in diagnostics["historical_sources"]:
    assert source in [{key: value for key, value in original.items() if key != "rows"}
                      for original in provenance["sources"]]
for row in summary:
    if row["method"] == "noRAG":
        continue
    method = row["method"]
    assert math.isclose(diagnostics["historical"][method]["global_score_mean"], float(row["Global_Score"]))
for method in ["B", "C"]:
    comparison = diagnostics["paired_comparisons"][f"A_minus_{method}"]
    assert comparison["wins"] + comparison["losses"] + comparison["ties"] == 100
    assert math.isclose(sum(comparison["weighted_metric_contributions"].values()),
                        comparison["mean_difference"], abs_tol=.002)
print("OK: notebook, prompts, notas, metadados e diagnóstico conferidos sem APIs.")
