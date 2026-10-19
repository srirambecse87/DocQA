"""CLI: python main.py [--examples | --question "..."]  (no flag = interactive)."""
import argparse
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from qa_engine import DocsQA, DocsQAError, GENERIC_ERROR, load_docs

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "docs" / "case-study-5-docs-qa-assistant" / "starter_kit" / "data"
DOCS_PATH = DATA_DIR / "docs.json"
EXAMPLES_PATH = DATA_DIR / "example_questions.json"


def setup_logging():
    root = logging.getLogger("docs_qa")
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.ERROR)
    console.setFormatter(fmt)
    root.addHandler(console)
    try:
        log_dir = BASE / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "docs_qa.log"
        file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
        try:
            os.chmod(log_file, 0o600)  # owner-only; limited effect on Windows
        except OSError:
            pass
    except OSError as exc:
        root.error("File logging disabled (%s); continuing with console logging only.", exc.strerror)


def show(ans):
    print(ans.text)
    for s in ans.sources:
        print(f"  source: {s.doc_id} - {s.title} (score {s.score})")
    print(f"  trace id: {ans.request_id}")


def run_examples(qa):
    try:
        examples = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))["example_questions"]
    except (OSError, ValueError, KeyError) as exc:
        raise DocsQAError("Example questions file is missing or malformed.") from exc
    passed = 0
    for ex in examples:
        ans = qa.ask(ex["question"])
        got = ans.sources[0].doc_id if ans.answered else None
        ok = got == ex["expected_doc_id"]
        passed += ok
        print(f"\n[{'PASS' if ok else 'FAIL'}] {ex['question_id']}: {ex['question']}")
        show(ans)
    print(f"\n{passed}/{len(examples)} passed")
    return 0 if passed == len(examples) else 1


def main():
    parser = argparse.ArgumentParser(description="Docs Q&A assistant")
    parser.add_argument("--question", help="ask a single question")
    parser.add_argument("--examples", action="store_true", help="run the example questions")
    args = parser.parse_args()

    setup_logging()
    log = logging.getLogger("docs_qa")
    try:
        qa = DocsQA(load_docs(DOCS_PATH))
        if args.examples:
            return run_examples(qa)
        if args.question:
            show(qa.ask(args.question))
            return 0
        print("Ask a question (blank line or Ctrl+C to quit).")
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not line.strip():
                return 0
            show(qa.ask(line))
    except DocsQAError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception:
        log.exception("fatal error")
        print(GENERIC_ERROR, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
