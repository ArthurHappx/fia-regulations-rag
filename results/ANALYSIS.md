# Granularidade, orçamento de recuperação e interpretação dos resultados

Esta análise foi acrescentada em **04/11/2026**, após o encerramento do trabalho acadêmico. Usa o código local atual para medir o corpus e os CSVs históricos para medir contextos e notas. Não reexecuta recuperação, geração ou juízes.

## A justificativa de `k` e `top_k` estava documentada?

Foram conduzidos experimentos ad-hoc de calibração para os valores de `k` e `top_k`. A principal intuição considerada foi de que **unidades menores (maior granularidade) podem exigir mais candidatos e mais unidades selecionadas para reunir evidências suficientes**. Isso justifica avaliar configurações diferentes por estratégia. Contudo, não demonstra que os valores escolhidos igualaram a informação disponível ou foram ótimos.

| Método | `k`: candidatos recuperados | `top_k`: unidades após reranking |
| --- | ---: | ---: |
| A (Standard) | 60 | 8 |
| B (Fine grained) | 80 | 10 |
| C (Coarse grained) | 60 | 8 |

Variar esses limites pode ser adequado para comparar pipelines ajustados à sua granularidade. A ressalva metodológica deve ser específica: a comparação conjunta de **pré-processamento e política de recuperação** não mede o efeito isolado de trocar somente o pré-processamento. Uma comparação com orçamento final de tokens equivalente seria outro experimento, não necessariamente uma exigência de usar o mesmo número de chunks.

## O que foi efetivamente medido

Os tokens abaixo são contados com o tokenizer local de `all-MiniLM-L6-v2`, sem truncamento e sem executar o modelo. São uma medida consistente entre métodos; não são a contagem exata de tokens do LLM gerador.

| Medida dos 100 contextos históricos | A | B | C |
| --- | ---: | ---: | ---: |
| Caracteres, média | 7.813,24 | 4.874,48 | 10.317,44 |
| Caracteres, mediana | 7.885 | 3.947 | 6.768,5 |
| Tokens, média | 1.672,61 | 1.013,07 | 2.336,68 |
| Tokens, mediana | 1.662 | 859 | 1.406 |
| Caracteres, máximo | 9.384 | 20.163 | 119.415 |
| Respostas com a frase de abstenção | 34 | 37 | 40 |

O aumento de `top_k` de B de 8 para 10 não igualou o volume médio de contexto observado em A: B recebeu aproximadamente **39,4% menos tokens**. Volume é uma aproximação; tokens adicionais podem conter repetição ou material irrelevante e não equivalem automaticamente a mais informação útil.

Para C, a afirmação de que sempre recupera menos conteúdo seria incorreta. A mediana é menor que a de A, mas a média é maior e influenciada por extremos. C combina unidades curtas com algumas muito extensas.

No corpus reconstruído pelo código atual:

| Medida por documento | A | B | C |
| --- | ---: | ---: | ---: |
| Número de unidades | 1.282 | 3.716 | 1.340 |
| Caracteres, mediana | 1.125 | 228 | 373,5 |
| Caracteres, máximo | 1.199 | 12.581 | 111.481 |
| Unidades acima de 256 tokens | 412 | 172 | 200 |
| Unidades acima de 512 tokens, sem contar a pergunta | 28 | 38 | 62 |

## Por que A pode ter obtido a maior média

As observações sustentam hipóteses de implementação e de orçamento, sem identificar uma causa única.

### 1. Fragmentação e perda de contexto em B

Unidades pequenas podem aumentar a precisão da localização e, ao mesmo tempo, separar uma regra de suas exceções, definições e condições. O método A preserva vizinhança por chunks maiores e sobreposição de 150 caracteres. B não expande automaticamente o item recuperado para sua cláusula pai ou seus vizinhos.

O contexto menor observado em B é compatível com essa hipótese. A localização de um item mais específico não garante que todos os itens necessários à resposta estejam entre os dez selecionados. Demonstrar esse mecanismo exigiria anotar evidências relevantes por pergunta e medir sua recuperação.

### 2. Metadados estruturados não chegam ao gerador

O método B armazena artigo e cláusula em `Document.metadata`. Contudo, `generate_answer` monta o contexto somente com `doc.page_content`, e o reranking também recebe apenas esse texto. Assim, o pipeline não aproveita diretamente os campos estruturados para informar fonte, hierarquia e identificador ao gerador.

No corpus atual de B, o valor completo do campo `clause` não aparece no texto de 2.149 das 3.716 unidades. Isso mede uma ocorrência literal, não a ausência de toda referência possível. Ainda assim, a omissão dos metadados pelo código é inequívoca e merece atenção porque o prompt exige citações de artigos.

Um exemplo histórico é a pergunta 2, sobre o número máximo de competições: o contexto de **todos os métodos contém a informação correta**. A e C respondem diretamente com A2.1.2. B também termina com a resposta correta e recebe corretude 100, mas discute primeiro artigos de outros assuntos; sua densidade recebe 88, contra 100 de A e C. Esse caso ilustra confusão de atribuição e verbosidade, não uma falha factual da busca nem uma explicação de toda a diferença média.

### 3. O método C não produz somente cláusulas bem delimitadas

No corpus atual, a unidade identificada como `A9.8.3` contém **111.481 caracteres**, cerca de **34.426 tokens** deste tokenizer. O primeiro marcador `APPENDIX` aparece no caractere 418 e há nove ocorrências desse marcador. O extrator acaba agregando material de apêndices à última cláusula, porque sua divisão depende do padrão de numeração das cláusulas.

Isso pode gerar ruído no contexto e representações pouco específicas. O [modelo de embeddings](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) é voltado a sentenças e parágrafos curtos e trunca entradas acima de 256 word pieces por padrão. Uma unidade muito longa pode ser buscada com base apenas em seu início, embora seu texto inteiro seja enviado ao gerador se selecionada. A incidência e o impacto histórico exatos não foram reconstruídos.

O truncamento não é exclusivo de C: A tem até mais unidades acima de 256 tokens. O problema específico observado em C é a severidade de alguns extremos e a mistura de cláusula e apêndices, não uma demonstração de que todo chunk de A cabe no modelo.

### 4. Os pesos favorecem corretude e recall, onde A foi melhor

B obteve densidade de informação média **69,32**, superior aos **68,32** de A. Isso é compatível com respostas mais focadas, mas não compensou as diferenças nas métricas de maior peso.

| Parcela da diferença de score global | A − B | A − C |
| --- | ---: | ---: |
| Coerência × 0,1 | +0,385 | +0,315 |
| Relevância × 0,2 | +0,656 | +1,184 |
| Densidade × 0,1 | −0,100 | +0,904 |
| Corretude × 0,4 | +1,656 | +1,648 |
| Recall × 0,2 | +0,858 | +1,142 |
| **Total** | **+3,455** | **+5,193** |

Portanto, A venceu pela combinação das métricas, principalmente por corretude e recall, e não porque superou B em todos os critérios.

## A vantagem é robusta?

| Comparação de score global por pergunta | Vitórias de A | Derrotas de A | Empates | Diferença média | Intervalo exploratório de 95% |
| --- | ---: | ---: | ---: | ---: | --- |
| A − B | 57 | 40 | 3 | +3,455 | [−2,742; +9,576] |
| A − C | 51 | 46 | 3 | +5,193 | [−1,622; +12,111] |

Os intervalos são de um **bootstrap pareado pós-hoc**: 10.000 reamostragens das 100 diferenças por pergunta, semente 20261104, percentis 2,5 e 97,5. Ambos incluem zero. Não constituem evidência de superioridade geral de A; também não comprovam equivalência entre os métodos. A comparação com C, em particular, tem praticamente o mesmo número de vitórias e derrotas, embora as magnitudes dos ganhos e perdas difiram.

Essa reamostragem descreve sensibilidade à composição do conjunto disponível. As perguntas são sintéticas, não uma amostra aleatória de todos os usos do sistema.

## Interpretação e próximos experimentos

Esperar que B ou C melhore a localização é uma hipótese razoável. Para converter esse potencial em respostas melhores, é necessário preservar contexto suficiente e efetivamente usar a estrutura extraída. **Mais granularidade não garante, por si só, melhor resultado de ponta a ponta.** Os achados atuais são compatíveis com uma vantagem de A na preservação de contexto e com limitações da implementação dos métodos estruturados; não refutam o uso de dados estruturados em RAG.

Uma sequência de experimentos capaz de testar essas explicações seria:

1. Separar apêndices e limitar unidades excessivas por tokens em C; validar cobertura e hierarquia antes da indexação.
2. Acrescentar artigo, cláusula, título e origem (metadados) ao texto enviado ao gerador e testar esse recurso isoladamente em B e C.
3. Recuperar itens finos e expandi-los com cláusula pai ou vizinhos (grafos de relacionamento podem ser úteis), medindo quais evidências adicionais ajudam.
4. Comparar estratégias com o mesmo orçamento final de tokens e ajustar `k`/`top_k` em um conjunto de validação separado. Fazer também uma comparação com os parâmetros fixos para isolar a troca do pré-processamento.
5. Anotar evidências necessárias por pergunta e medir recuperação antes e depois do reranking, além de comparar qualidade final, latência e custo. Repetir gerações e avaliações com modelos e prompts fixos.

São propostas de novos experimentos; nenhuma dessas modificações foi aplicada retroativamente às notas históricas.

## Reprodução do diagnóstico

Prepare o ambiente conforme o [README principal](../README.md#executar-localmente) e execute na raiz do projeto.

**Windows / PowerShell**

```powershell
.\.venv\Scripts\python.exe scripts/analyze_retrieval.py
```

**Linux / Bash**

```bash
./.venv/bin/python scripts/analyze_retrieval.py
```

As instruções para Linux ainda não foram validadas nesse sistema.

São necessários os dados locais em `filesIAColab/`, os CSVs completos em `backups/avaliacoes/` e o tokenizer já presente no cache local. O script não faz chamadas a APIs nem baixa modelos. O [relatório agregado](analysis/retrieval_diagnostics.json) inclui as métricas, os hashes das fontes e as limitações; não publica perguntas, respostas ou trechos dos regulamentos. As notas originais em `historical/` permanecem inalteradas.
