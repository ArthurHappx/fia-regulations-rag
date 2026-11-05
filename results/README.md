# Resultados históricos

Os arquivos em `historical/` foram derivados de quatro CSVs locais (`avaliacao_{a,b,c,noRAG}_final.csv`). Cada método contém 100 perguntas; a ordem e o texto das perguntas foram conferidos entre os métodos, e todas as notas estão entre 0 e 100.

- `scores.csv`: notas por método e posição da pergunta, sem respostas ou trechos dos regulamentos.
- `summary.csv`: médias das cinco métricas e do score global.
- `comparison.png`: comparação descritiva dos três métodos RAG.
- `provenance.json`: hashes SHA-256 dos CSVs de origem, pesos e limitações.

Os CSVs completos permanecem locais: contêm contexto recuperado dos documentos de terceiros. O resumo pode ser conferido a partir de `scores.csv`, sem chaves de API. Para regenerar a exportação a partir dos arquivos completos, prepare o ambiente conforme o [README principal](../README.md#executar-localmente) e execute na raiz do projeto:

**Windows / PowerShell**

```powershell
.\.venv\Scripts\python.exe scripts/summarize_results.py --input-dir backups/avaliacoes
.\.venv\Scripts\python.exe scripts/plot_results.py
```

**Linux / Bash**

```bash
./.venv/bin/python scripts/summarize_results.py --input-dir backups/avaliacoes
./.venv/bin/python scripts/plot_results.py
```

As instruções para Linux ainda não foram validadas nesse sistema. Os CSVs de origem em `backups/avaliacoes/` são necessários para a exportação; somente a figura pode ser regenerada diretamente com os resumos publicados.

O score global é `0,4 × corretude + 0,2 × relevância + 0,2 × recall + 0,1 × coerência + 0,1 × densidade`. Esse peso é uma escolha deste projeto; não é apresentado como validação do artigo CCRS.

As notas não são porcentagens de acerto. São avaliações de um LLM, sujeitas a vieses e à qualidade das respostas de referência.

O resultado histórico sem RAG está preservado nos arquivos de notas, mas exige cautela: o código reutilizava o prompt restrito ao contexto mesmo sem fornecer contexto. A versão atual (disponibilizada após a finalização do projeto) corrige esse comportamento para novas execuções. A configuração exata dos modelos históricos não está registrada nos CSVs; os modelos atuais não representam uma reprodução exata desses resultados.

Uma [análise posterior](ANALYSIS.md), de 04/11/2026, mede tamanhos dos contextos, examina limitações do código e acrescenta intervalos exploratórios por bootstrap pareado. Os intervalos das diferenças A−B e A−C incluem zero; não foi demonstrada superioridade geral de A. O diagnóstico não reexecuta modelos nem modifica as notas históricas.
