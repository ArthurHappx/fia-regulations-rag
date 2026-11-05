"""Diagnóstico offline de granularidade e resultados; não reexecuta busca ou LLMs.

Requer os dados locais, os quatro CSVs históricos e o tokenizer já baixado.
O relatório exporta somente agregados, hashes e identificadores de cláusulas.
"""

import argparse
import ast
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from statistics import mean, median

import numpy as np
from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = {"Context_Coherence_Score": .1, "Question_Relevance_Score": .2,
           "Information_Density_Score": .1, "Answer_Correctness_Score": .4,
           "Information_Recall_Score": .2}


def sizes(values):
    return {"mean": round(mean(values), 3), "median": median(values),
            "p90": float(np.percentile(values, 90)), "min": min(values), "max": max(values)}


def score(row):
    return sum(float(row[key]) * weight for key, weight in WEIGHTS.items())


def abstains(answer):
    plain = "".join(c for c in unicodedata.normalize("NFD", answer.lower()) if not unicodedata.combining(c))
    return "nao foi possivel" in plain


def notebook_parameters(cells, variable):
    for cell in cells:
        if cell["cell_type"] != "code":
            continue
        for node in ast.walk(ast.parse("".join(cell["source"]))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "process_json_questions_range":
                continue
            arguments = {kw.arg: kw.value for kw in node.keywords}
            store = arguments.get("vector_store")
            if isinstance(store, ast.Name) and store.id == variable and "end_idx" in arguments:
                if ast.literal_eval(arguments["end_idx"]) == 100:
                    return {key: ast.literal_eval(arguments[key]) for key in ["k", "top_k"]}
    raise ValueError(f"Lote completo não encontrado: {variable}")


def analyze(input_dir, output):
    notebook_path = ROOT / "FIA_Regulation_RAG.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    scope = {}
    # Reutiliza o pré-processamento efetivo do notebook, sem embeddings ou APIs.
    for index in [6, 8, 10]:
        exec("".join(notebook["cells"][index]["source"]), scope)
    cache = ROOT / ".cache/huggingface"
    tokenizer = AutoTokenizer.from_pretrained(
        "sentence-transformers/all-MiniLM-L6-v2", cache_dir=str(cache / "hub"), local_files_only=True,
    )
    tokenizer.model_max_length = 10**9  # Mede texto integral, sem truncar ou executar o modelo.

    def tokens(text):
        return len(tokenizer.encode(text, add_special_tokens=True, truncation=False))

    methods = {"A": "chunks_method_a", "B": "documents_to_index", "C": "documents_method_c"}
    corpus, historical, records, sources = {}, {}, {}, []
    for method, name in methods.items():
        docs = scope[name]
        token_lengths = [tokens(doc.page_content) for doc in docs]
        corpus[method] = {
            "documents": len(docs), "characters": sizes([len(doc.page_content) for doc in docs]),
            "embedding_tokenizer_tokens": sizes(token_lengths),
            "documents_over_256_tokens": sum(value > 256 for value in token_lengths),
            "documents_over_512_tokens": sum(value > 512 for value in token_lengths),
        }
        if method in ["B", "C"]:
            key = "clause" if method == "B" else "clause_id"
            corpus[method]["own_clause_id_present_in_text"] = sum(
                bool(doc.metadata.get(key)) and doc.metadata[key] in doc.page_content for doc in docs
            )
            longest = max(docs, key=lambda doc: len(doc.page_content))
            corpus[method]["longest_clause_id"] = longest.metadata.get(key)
            corpus[method]["appendix_markers_in_longest_document"] = longest.page_content.count("APPENDIX")
            corpus[method]["first_appendix_offset_in_longest_document"] = longest.page_content.find("APPENDIX")
        path = input_dir / f"avaliacao_{method.lower()}_final.csv"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if records and [row["Pergunta"] for row in rows] != [row["Pergunta"] for row in records["A"]]:
            raise ValueError("Perguntas ou ordem diferentes entre CSVs")
        records[method] = rows
        historical[method] = {
            "questions": len(rows),
            "context_characters": sizes([len(row["Contexto_Recuperado"]) for row in rows]),
            "context_embedding_tokenizer_tokens": sizes([tokens(row["Contexto_Recuperado"]) for row in rows]),
            "abstention_phrase_count": sum(abstains(row["Resposta_Gerada"]) for row in rows),
            "global_score_mean": round(mean(score(row) for row in rows), 3),
            "metrics_mean": {key: round(mean(float(row[key]) for row in rows), 3) for key in WEIGHTS},
        }
        sources.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

    comparisons = {}
    for method in ["B", "C"]:
        differences = np.array([score(a) - score(b) for a, b in zip(records["A"], records[method])])
        rng = np.random.default_rng(20261104)
        means = rng.choice(differences, size=(10000, len(differences)), replace=True).mean(axis=1)
        comparisons[f"A_minus_{method}"] = {
            "wins": int(sum(differences > 1e-8)), "losses": int(sum(differences < -1e-8)),
            "ties": int(sum(abs(differences) <= 1e-8)), "mean_difference": round(float(differences.mean()), 3),
            "exploratory_paired_bootstrap_95_interval": [round(float(value), 3) for value in np.percentile(means, [2.5, 97.5])],
            "weighted_metric_contributions": {
                key: round(weight * (historical["A"]["metrics_mean"][key] - historical[method]["metrics_mean"][key]), 3)
                for key, weight in WEIGHTS.items()
            },
        }

    starts = {}
    for path in sorted((ROOT / "filesIAColab").glob("CLEAN_*.md")):
        text = path.read_text(encoding="utf-8")
        letter = path.name.split("_Regulations_")[1][0]
        position = text.find(f"## ARTICLE {letter}3", 100)
        starts[letter] = {"start_offset": position, "article_1_clause_present_in_C": any(
            re.match(fr"{letter}1\.", doc.metadata.get("clause_id", "")) for doc in scope["documents_method_c"]
        )}
    report = {
        "description": "Diagnóstico pós-hoc; corpus atual e contextos históricos não são a mesma execução.",
        "parameters_from_current_notebook_not_historical_metadata": {
            method: notebook_parameters(notebook["cells"], f"vector_store_{method.lower()}") for method in methods
        },
        "tokenizer": "sentence-transformers/all-MiniLM-L6-v2 (cache local; sem truncamento na medição)",
        "corpus": corpus, "historical": historical, "paired_comparisons": comparisons,
        "coarse_content_start_diagnostic": starts, "historical_sources": sources,
        "current_preprocessing_source_sha256": hashlib.sha256("\n".join(
            "".join(notebook["cells"][index]["source"]) for index in [6, 8, 10]
        ).encode("utf-8")).hexdigest(),
        "current_corpus_sources": [{"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                                   for path in sorted((ROOT / "filesIAColab").glob("CLEAN_*.md"))
                                   ] + [{"file": "fia_rag_chunks.jsonl", "sha256": hashlib.sha256(
                                       (ROOT / "filesIAColab/fia_rag_chunks.jsonl").read_bytes()).hexdigest()}],
        "illustrative_question_2": {
            method: {
                "relevant_24_competitions_sentence_in_context": bool(re.search(
                    r"maximum number of Competitions.*?24", records[method][1]["Contexto_Recuperado"], re.S)),
                "answer_characters": len(records[method][1]["Resposta_Gerada"]),
                "correctness_score": float(records[method][1]["Answer_Correctness_Score"]),
                "density_score": float(records[method][1]["Information_Density_Score"]),
            } for method in methods
        },
        "limitations": [
            "Caracteres e tokens deste tokenizer não medem tokens exatos do LLM gerador.",
            "Medições atuais do corpus não comprovam a versão usada nos CSVs históricos.",
            "A frase de abstenção é uma heurística, não uma classificação de corretude.",
            "Bootstrap pareado pós-hoc: reamostra perguntas; não mede variabilidade dos modelos ou generalização.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "backups/avaliacoes")
    parser.add_argument("--output", type=Path, default=ROOT / "results/analysis/retrieval_diagnostics.json")
    args = parser.parse_args()
    analyze(args.input_dir, args.output)
