"""Retrieval-only docs Q&A engine: answers come verbatim from the docs or not at all."""
import hashlib
import json
import logging
import math
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("docs_qa")

MAX_QUESTION_CHARS = 500
MAX_DOCS_FILE_BYTES = 5 * 1024 * 1024
MIN_COVERAGE = 0.5
NO_ANSWER = "I don't have an answer for that in the documentation."
GENERIC_ERROR = "Sorry, something went wrong while looking that up. Please try again."

STOPWORDS = frozenset(
    "a an the is are was were be do does did can could should would will i me my we our you your "
    "how what when where which who why to of in on for with and or if it its this that there "
    "long much many number maximum use have has get about before after any".split()
)


class DocsQAError(Exception):
    """Expected, user-safe failure (bad input or bad data)."""


@dataclass
class Source:
    doc_id: str
    title: str
    score: float


@dataclass
class Answer:
    request_id: str
    answered: bool
    text: str
    score: float = 0.0
    sources: list = field(default_factory=list)


def _stem(tok):
    for suffix in ("ing", "ed", "es", "s"):
        if tok.endswith(suffix) and len(tok) - len(suffix) >= 3:
            return tok[: -len(suffix)]
    return tok


def tokenize(text):
    return [_stem(t) for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def sanitize_question(question):
    if not isinstance(question, str):
        raise DocsQAError("Question must be text.")
    # Cc/Cf cover control chars and invisible formatting such as bidi overrides.
    normalized = unicodedata.normalize("NFKC", question)
    cleaned = "".join(" " if unicodedata.category(ch) in ("Cc", "Cf") else ch for ch in normalized).strip()
    if not cleaned:
        raise DocsQAError("Please enter a question.")
    if len(cleaned) > MAX_QUESTION_CHARS:
        raise DocsQAError(f"Question is too long (max {MAX_QUESTION_CHARS} characters).")
    return cleaned


def load_docs(path):
    p = Path(path)
    try:
        if p.stat().st_size > MAX_DOCS_FILE_BYTES:
            raise DocsQAError("Docs file is unexpectedly large.")
        data = json.loads(p.read_text(encoding="utf-8"))
        docs = data["docs"]
        if not isinstance(docs, list) or not docs:
            raise KeyError("no docs")
        for d in docs:
            if not all(isinstance(d[k], str) for k in ("doc_id", "title", "content")):
                raise KeyError("non-string field")
    except DocsQAError:
        raise
    except FileNotFoundError:
        raise DocsQAError(f"Docs file not found: {p.name}") from None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.error("Failed to load docs from %s: %r", p, exc)
        raise DocsQAError("Docs file is missing or malformed.") from exc
    logger.info("Loaded %d docs from %s", len(docs), p.name)
    return docs


class DocsQA:
    def __init__(self, docs):
        self.chunks = []
        for doc in docs:
            title_tokens = set(tokenize(doc["title"]))
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", doc["content"]) if s.strip()]
            for idx, sentence in enumerate(sentences):
                self.chunks.append({
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "idx": idx,
                    "text": sentence,
                    "own": set(tokenize(sentence)),
                    "tokens": set(tokenize(sentence)) | title_tokens,
                })
        n = len(self.chunks)
        df = {}
        for c in self.chunks:
            for t in c["tokens"]:
                df[t] = df.get(t, 0) + 1
        self._n = n
        self._idf = {t: math.log(1 + n / f) for t, f in df.items()}
        self._unknown_idf = math.log(1 + n)  # unseen terms count against coverage

    def _score(self, q_terms, chunk):
        total = sum(self._idf.get(t, self._unknown_idf) for t in q_terms)
        matched = sum(self._idf[t] for t in q_terms if t in chunk["tokens"])
        return matched / total if total else 0.0

    def ask(self, question):
        request_id = uuid.uuid4().hex[:8]
        try:
            q = sanitize_question(question)
            qhash = hashlib.sha256(q.encode("utf-8", "replace")).hexdigest()[:10]
            # Log a hash, not the raw text, since questions may contain personal data.
            logger.info("[%s] question received hash=%s len=%d", request_id, qhash, len(q))
            q_terms = set(tokenize(q))
            if not q_terms:
                logger.info("[%s] no content terms -> no answer", request_id)
                return Answer(request_id, False, NO_ANSWER)

            # Ties go to the sentence that itself contains more query terms (not just the title).
            scored = sorted(((self._score(q_terms, c), c) for c in self.chunks),
                            key=lambda p: (p[0], len(q_terms & p[1]["own"])), reverse=True)
            best_score, best = scored[0]
            if best_score < MIN_COVERAGE:
                logger.info("[%s] best=%s score=%.2f < %.2f -> no answer",
                            request_id, best["doc_id"], best_score, MIN_COVERAGE)
                return Answer(request_id, False, NO_ANSWER, best_score)

            # Add other sentences from the same doc that also clear the bar.
            same_doc = [c for s, c in scored if c["doc_id"] == best["doc_id"] and s >= MIN_COVERAGE]
            picked = sorted(same_doc[:2], key=lambda c: c["idx"])
            text = " ".join(c["text"] for c in picked)
            logger.info("[%s] answered from %s score=%.2f chunks=%s", request_id, best["doc_id"],
                        best_score, [c["idx"] for c in picked])
            return Answer(request_id, True, text, best_score,
                          [Source(best["doc_id"], best["title"], round(best_score, 2))])
        except DocsQAError as exc:
            logger.warning("[%s] rejected input: %s", request_id, exc)
            return Answer(request_id, False, str(exc))
        except Exception:
            logger.exception("[%s] unexpected error", request_id)
            return Answer(request_id, False, GENERIC_ERROR)
