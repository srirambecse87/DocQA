"""Compares the starter kit's retrieval (docs_qa_utils) with our engine (qa_engine) on the same questions."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STARTER = ROOT / "docs" / "case-study-5-docs-qa-assistant" / "starter_kit"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(STARTER))

import docs_qa_utils as starter  # noqa: E402
from qa_engine import DocsQA, NO_ANSWER, load_docs  # noqa: E402

DOCS_PATH = STARTER / "data" / "docs.json"
EXAMPLES = json.loads((STARTER / "data" / "example_questions.json").read_text(encoding="utf-8"))["example_questions"]

# Extra questions covering docs the starter cannot index or text it truncates.
EXTRA = [
    ("How do I invite a new team member?", "D-02", "doc under 400 chars -> zero starter chunks"),
    ("Does Solstice support SAML SSO?", "D-05", "doc under 400 chars -> zero starter chunks"),
    ("How long are CSV exports retained?", "D-03", "fact sits mid-doc"),
]


def starter_answer(chunks, question, min_score=0.0):
    """Starter behaviour: top chunk wins; it has no abstention, so any positive score 'answers'."""
    best = starter.find_best_chunks(question, chunks, top_n=1)
    if best and best[0][0] > min_score:
        return best[0][1]["doc_id"], best[0][1]["text"]
    return None, None


class ComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs = load_docs(DOCS_PATH)
        cls.docs = {d["doc_id"]: d["content"] for d in docs}
        cls.chunks = starter.chunk_all_docs(starter.load_docs(DOCS_PATH))
        cls.qa = DocsQA(docs)

    def test_starter_chunking_loses_content(self):
        covered = {c["doc_id"] for c in self.chunks}
        self.assertEqual(covered, {"D-01", "D-03", "D-04", "D-06"}, "starter skips docs under 400 chars")
        kept = sum(len(c["text"]) for c in self.chunks)
        total = sum(len(t) for t in self.docs.values())
        self.assertLess(kept, total)
        # Our chunks cover every character of every doc.
        ours = {d: " ".join(c["text"] for c in self.qa.chunks if c["doc_id"] == d) for d in self.docs}
        for doc_id, content in self.docs.items():
            self.assertEqual(ours[doc_id].split(), content.split(), doc_id)

    def test_engine_answers_all_examples_correctly(self):
        for ex in EXAMPLES:
            ans = self.qa.ask(ex["question"])
            got = ans.sources[0].doc_id if ans.answered else None
            self.assertEqual(got, ex["expected_doc_id"], ex["question_id"])

    def test_engine_abstains_where_starter_guesses(self):
        q5 = next(e for e in EXAMPLES if e["expected_doc_id"] is None)["question"]
        doc_id, _ = starter_answer(self.chunks, q5)
        self.assertIsNotNone(doc_id, "starter returns a passage even though docs don't cover the question")
        ans = self.qa.ask(q5)
        self.assertFalse(ans.answered)
        self.assertEqual(ans.text, NO_ANSWER)

    def test_engine_finds_docs_the_starter_cannot(self):
        for question, expected, _reason in EXTRA:
            ans = self.qa.ask(question)
            self.assertTrue(ans.answered, question)
            self.assertEqual(ans.sources[0].doc_id, expected, question)

    def test_engine_returns_the_exact_fact_not_just_the_right_doc(self):
        facts = {
            "What's the maximum number of rows I can export to CSV?": "10,000",
            "How long do I have to use a password reset link before it expires?": "15 minutes",
            "What are the API rate limits for the Growth plan?": "60 requests per minute",
        }
        for question, fact in facts.items():
            self.assertIn(fact, self.qa.ask(question).text, question)

    @unittest.expectedFailure
    def test_known_limitation_synonyms(self):
        # Docs say 'retained'/'deleted'; lexical matching can't bridge 'kept'/'deletion' (embeddings could).
        self.assertTrue(self.qa.ask("How long are CSV exports kept before deletion?").answered)

    def test_print_scorecard(self):
        rows = [(e["question"], e["expected_doc_id"]) for e in EXAMPLES]
        rows += [(q, d) for q, d, _ in EXTRA]
        facts = {"What's the maximum number of rows I can export to CSV?": "10,000",
                 "How long do I have to use a password reset link before it expires?": "15 minutes",
                 "What are the API rate limits for the Growth plan?": "60 requests per minute"}
        s_ok = e_ok = s_fact = e_fact = 0
        print("\n")
        for q, expected in rows:
            s_doc, s_text = starter_answer(self.chunks, q)
            ans = self.qa.ask(q)
            e_doc = ans.sources[0].doc_id if ans.answered else None
            s_ok += s_doc == expected
            e_ok += e_doc == expected
            if q in facts:
                s_fact += bool(s_text and facts[q] in s_text)
                e_fact += facts[q] in ans.text
            print(f"Q: {q}   (expected: {expected or 'no answer'})")
            print(f"  starter [{'ok' if s_doc == expected else 'WRONG'}] {s_doc}: {s_text or '(no answer)'}")
            print(f"  engine  [{'ok' if e_doc == expected else 'WRONG'}] {e_doc}: {ans.text}\n")
        print(f"\nCorrect doc/abstain: starter {s_ok}/{len(rows)}, engine {e_ok}/{len(rows)}")
        print(f"Exact fact present in answer: starter {s_fact}/{len(facts)}, engine {e_fact}/{len(facts)}")
        self.assertGreater(e_ok, s_ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
