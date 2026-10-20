# Docs Q&A Assistant

Answers admin questions using only Solstice's documentation, and says "I don't have an answer for that" when the docs don't cover it. Retrieval-only, no LLM. See [SOLUTION_DESIGN.md](SOLUTION_DESIGN.md) for the design and trade-offs.

## Requirements

Python 3.10+ (developed on 3.14). Standard library only; no installs needed.

## Run

From this folder:

```
python src\main.py --examples                    # run the 5 example questions with pass/fail
python src\main.py --question "How do I reset my password?"
python src\main.py                               # interactive; blank line to quit
```

Each answer shows the source document, a score and a trace ID. Use the trace ID to find the request in `logs/docs_qa.log`.

## Test

```
python -m unittest discover -s tests
python tests\test_comparison.py ComparisonTests.test_print_scorecard   # starter vs engine, with full responses
```

On PowerShell, unittest writes to stderr, so the shell may show exit code 1 even when tests pass. Check the "OK" line.

## Layout

```
src/qa_engine.py     retrieval engine: chunking, scoring, abstention, validation, logging
src/main.py          command-line interface and logging setup
tests/               accuracy, starter-vs-engine comparison, security and error-handling tests
docs/                case-study brief and starter kit (data/docs.json, example_questions.json)
logs/                runtime logs (git-ignored)
```

## Behavior summary

- Splits docs into sentences, scores them by the share of the question's rare/important words they contain, and answers only above a 50% coverage threshold.
- Answers are verbatim doc sentences, so nothing is generated or made up.
- Starter kit comparison: 8/8 vs 5/8 correct doc or abstention; exact fact present in 3/3 vs 0/3 answers.

## Security and reliability

- Questions are length-limited and cleaned of control and invisible characters; they are never executed.
- The docs file is size-checked and schema-validated.
- Errors show friendly messages; details and stack traces go only to the log.
- Logs contain a hash of the question and a trace ID, never the question text.

## Known limitations

- Word matching only: synonyms ("kept" vs "retained") are missed. Embeddings would fix this.
- Sentence-level answers can miss context from other sentences.
- The 50% threshold was tuned on a small question set.
- CLI only, with no authentication or rate limiting.
- English only; no conversation memory.

## Next steps

Planned in five phases (see section 8 of [SOLUTION_DESIGN.md](SOLUTION_DESIGN.md)): multi-format ingestion (PDF, Word, Markdown, text), embeddings with Chroma, an LLM answer layer that stays grounded in retrieved passages, a response cache, and a UI with feedback collection. The abstention check always runs before any LLM call.
