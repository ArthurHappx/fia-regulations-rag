"""Exporta apenas notas agregadas e por pergunta, sem textos dos regulamentos."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
METRICS = {
    "Context_Coherence_Score": 0.1,
    "Question_Relevance_Score": 0.2,
    "Information_Density_Score": 0.1,
    "Answer_Correctness_Score": 0.4,
    "Information_Recall_Score": 0.2,
}
FILES = {"A": "avaliacao_a_final.csv", "B": "avaliacao_b_final.csv",
         "C": "avaliacao_c_final.csv", "noRAG": "avaliacao_noRAG_final.csv"}


def export(input_dir, output_dir):
    scores, summary, sources = [], [], []
    questions = None
    for method, filename in FILES.items():
        path = input_dir / filename
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        current_questions = [row["Pergunta"] for row in rows]
        if not rows or len(set(current_questions)) != len(rows):
            raise ValueError(f"Perguntas vazias ou duplicadas: {filename}")
        if questions is not None and current_questions != questions:
            raise ValueError(f"Perguntas ou ordem diferentes: {filename}")
        questions = current_questions
        method_scores = []
        for index, row in enumerate(rows, start=1):
            values = {key: float(row[key]) for key in METRICS}
            if not all(0 <= value <= 100 for value in values.values()):
                raise ValueError(f"Nota inválida: {filename}, pergunta {index}")
            values["Global_Score"] = sum(values[key] * weight for key, weight in METRICS.items())
            record = {"method": method, "question_id": index, **values}
            scores.append(record)
            method_scores.append(record)
        summary.append({"method": method, "n_questions": len(rows), **{
            key: round(mean(row[key] for row in method_scores), 3)
            for key in [*METRICS, "Global_Score"]
        }})
        sources.append({"file": filename, "rows": len(rows),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, records in [("scores.csv", scores), ("summary.csv", summary)]:
        with (output_dir / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=records[0])
            writer.writeheader()
            writer.writerows(records)
    (output_dir / "provenance.json").write_text(json.dumps({
        "description": "Notas extraídas de quatro CSVs locais de avaliação, sem reexecutar modelos.",
        "academic_completion_date": "2026-03-05",
        "historical_model_configuration": "Não confirmada nos CSVs originais.",
        "question_id": "Posição 1-based; texto e ordem conferidos entre os quatro métodos.",
        "weights": METRICS,
        "sources": sources,
        "limitations": [
            "O prompt sem RAG no código recebido exige contexto e pode induzir abstenções.",
            "Coerência contextual não se aplica diretamente ao método sem contexto.",
            "Os modelos atuais não reproduzem necessariamente as notas históricas.",
        ],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Exportadas {len(scores)} notas por pergunta e {len(summary)} resumos para {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "backups" / "avaliacoes")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "historical")
    args = parser.parse_args()
    export(args.input_dir, args.output_dir)
