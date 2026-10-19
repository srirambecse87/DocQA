# Solution Design: Docs Q&A Assistant for Solstice Learning

## 1. Problem

New admins repeatedly ask the same support questions (password resets, export limits, billing, API limits). The answers already exist in the docs. Elena Torres (Head of Support) wants a plain-English question box that returns a real answer from the documentation. Her key requirement: **if the docs don't cover it, say "I don't have an answer" rather than guess.**

Success therefore means: right passage when the docs cover the question, and an honest abstention when they don't. Wrong-but-confident answers are the worst outcome.

## 2. Assumptions

- The corpus is small (6 articles) and mostly factual; users ask short, direct questions in English.
- Elena values trustworthiness over coverage. A false "I don't know" is acceptable; a made-up answer is not.
- Questions are not authenticated and may contain personal data (e.g. emails), so raw questions should not be stored.
- The docs are trusted internal content; user questions are untrusted input.
- v1 is a command-line tool. Hosting, a UI and auth are out of scope.
- No LLM is needed for v1. The brief calls it optional.

## 3. Approach

Retrieval only. The engine ([src/qa_engine.py](src/qa_engine.py)) never generates text, so it cannot hallucinate; every answer is a verbatim sentence from a doc.

1. **Chunk by sentence.** Each sentence is a unit, indexed together with its doc title.
2. **Normalize the question.** Lowercase, drop filler words, light stemming ("expires" matches "expire").
3. **Score by weighted coverage.** For each sentence: the share of the question's important terms it contains, weighting rare terms (IDF) more. Terms never seen in the docs count against the score.
4. **Abstain below a threshold.** If the best sentence covers less than 50% of the weighted question terms, return "I don't have an answer for that in the documentation."
5. **Return the best 1-2 sentences** from the winning doc, with the doc ID, title and score.

## 4. Why not the starter kit as-is

The starter's `docs_qa_utils.py` was used as a reference, not a dependency. [tests/test_comparison.py](tests/test_comparison.py) runs both on 8 questions:

| Measure | Starter | Engine |
|---|---|---|
| Right doc, or correct abstention | 5 / 8 | 8 / 8 |
| Exact fact in the answer | 0 / 3 | 3 / 3 |

Causes:

- **Chunking drops content.** Fixed 400-character chunks discard the remainder, so docs under 400 characters (D-02, D-05) have zero chunks and can never be found.
- **No abstention.** It always returns its top match, so "Can I connect Solstice to Salesforce?" returns an unrelated CSV passage.
- **Weak scoring.** Unweighted Jaccard overlap treats "the" like "password" and penalizes longer chunks.
- **Coarse answers.** A 400-character block often cuts off before the fact (e.g. "10,000 rows").

## 5. Trade-offs considered

| Decision | Chosen | Alternative | Reason |
|---|---|---|---|
| Answer generation | Verbatim sentences | LLM rewrite | Zero hallucination risk; simpler to defend. LLM is an upgrade path. |
| Matching | Lexical (IDF-weighted) | Embeddings | Fast, deterministic and explainable on 6 docs. Embeddings add cost and a non-determinism risk. |
| Abstention | Fixed 50% coverage threshold | Learned/calibrated | Tuned by hand on 8 questions, which is simple but small-sample. |
| Granularity | Sentence | Paragraph / sliding window | Gives precise facts; context across sentences can be lost. |
| Logging | Hash of question + trace ID | Full text | Questions may contain personal data. |

## 6. Reliability and security

- **Input validation:** type check, 500-character cap, control and invisible Unicode characters removed. Input is only tokenized, never executed or interpolated.
- **Safe data loading:** docs file size cap and schema validation; malformed files give a clear error.
- **Exception handling:** expected problems return friendly messages; unexpected errors are logged with a stack trace and the user sees only a generic message.
- **Traceability:** every request has a trace ID shown to the user and in all log lines (`logs/docs_qa.log`, rotating, owner-only permissions where supported).
- **Tests:** 17 tests in `tests/` cover accuracy, comparison with the starter, input abuse, bad data files and log content (raw question never logged).

## 7. Known limitations

- **No synonyms.** "How long are exports kept before deletion?" fails because the docs say "retained"/"deleted" (marked as an expected-failure test).
- **Sentence-level only.** Answers needing information from distant sentences may be partial.
- **Threshold is hand-tuned** on a very small set; more data could shift it.
- **No rate limiting or authentication**, since this is a CLI. Needed for a hosted service.
- English only; one-shot questions with no conversation context.

## 8. With more time, data or budget

1. **RAG pipeline (planned next):** ingest the original PDF and Word docs, embed into a vector store (Chroma), and add an optional LLM step that writes the answer using only retrieved passages, with citations. The abstention check runs first, so "don't know" never reaches the LLM.
2. **Semantic retrieval** to cover synonyms, combined with the lexical score (hybrid).
3. **Larger evaluation set** from real support tickets to calibrate the threshold and measure precision/recall of abstention.
4. **Hosting:** a small API with authentication, rate limiting and a feedback button ("was this helpful?") to find doc gaps.
5. **Doc-gap report:** aggregate abstained questions so Elena's team sees what the docs are missing.
