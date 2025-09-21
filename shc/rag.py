"""Retrieval-augmented generation helpers for Slum House Capital agents."""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import faiss
import numpy as np
import requests
from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency loading guard
    OpenAI = None  # type: ignore

LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_DIR = Path(os.getenv("SHC_INDEX_DIR", BASE_DIR / "data" / "index"))
INDEX_PATH = INDEX_DIR / "index.faiss"
META_PATH = INDEX_DIR / "meta.json"
EMBED_MODEL_NAME = os.getenv("SHC_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
NEMOTRON_MODEL = os.getenv("NEMOTRON_MODEL", "nemotron-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_STYLE_HINTS = {
    "concise": "Respond with 3-6 short lines focused on actionable trading education.",
    "bullets": "Respond with 2 short bullet points describing concrete risks.",
    "explainer": (
        "Respond with 8-12 short lines outlining thesis, entry, invalidation, risk, and traps."
    ),
}


@dataclass
class Chunk:
    """A chunk retrieved from the FAISS index."""

    doc_path: str
    shortname: str
    chunk: int
    text: str
    snippet: str
    score: float

    @property
    def label(self) -> str:
        return f"[{self.shortname} §{self.chunk + 1}]"


class _IndexState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.index: Optional[faiss.Index] = None
        self.meta: Dict[str, object] = {}
        self.chunk_cache: List[Dict[str, object]] = []
        self.model: Optional[SentenceTransformer] = None
        self.index_mtime: float = 0.0
        self.meta_mtime: float = 0.0

    def _load_model(self) -> SentenceTransformer:
        if self.model is None:
            LOGGER.info("Loading embedder %s", EMBED_MODEL_NAME)
            self.model = SentenceTransformer(EMBED_MODEL_NAME)
        return self.model

    def _meta_changed(self) -> bool:
        index_stat = INDEX_PATH.stat().st_mtime if INDEX_PATH.exists() else 0.0
        meta_stat = META_PATH.stat().st_mtime if META_PATH.exists() else 0.0
        return (index_stat != self.index_mtime) or (meta_stat != self.meta_mtime)

    def ensure(self) -> None:
        with self.lock:
            if not INDEX_PATH.exists() or not META_PATH.exists():
                self.index = None
                self.meta = {}
                self.chunk_cache = []
                return
            if self.index is not None and not self._meta_changed():
                return
            LOGGER.info("Loading FAISS index from %s", INDEX_PATH)
            self.index = faiss.read_index(str(INDEX_PATH))
            with META_PATH.open("r", encoding="utf-8") as fh:
                self.meta = json.load(fh)
            self.chunk_cache = self.meta.get("chunks", [])  # type: ignore[assignment]
            self.index_mtime = INDEX_PATH.stat().st_mtime
            self.meta_mtime = META_PATH.stat().st_mtime

    def embed(self, text: str) -> np.ndarray:
        model = self._load_model()
        vector = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)
        if vector.dtype != np.float32:
            vector = vector.astype("float32")
        return vector

    def as_chunk(self, idx: int, score: float) -> Optional[Chunk]:
        if idx < 0 or idx >= len(self.chunk_cache):
            return None
        raw = self.chunk_cache[idx]
        return Chunk(
            doc_path=raw.get("doc_path", ""),
            shortname=raw.get("shortname", "document"),
            chunk=int(raw.get("chunk", 0)),
            text=raw.get("text", ""),
            snippet=raw.get("snippet", ""),
            score=float(score),
        )


_STATE = _IndexState()


def _ensure_ready() -> bool:
    try:
        _STATE.ensure()
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Failed to load RAG index: %s", exc)
        return False
    if _STATE.index is None or not _STATE.chunk_cache:
        LOGGER.warning("RAG index not available. Did you run scripts/ingest_docs.py?")
        return False
    return True


def search(query: str, k: int = 6) -> List[Chunk]:
    if not query.strip():
        return []
    if not _ensure_ready():
        return []
    vector = _STATE.embed(query)
    assert _STATE.index is not None
    top_k = min(max(k * 2, k), len(_STATE.chunk_cache))
    scores, indices = _STATE.index.search(vector, top_k)
    chunks: List[Chunk] = []
    for idx, score in zip(indices[0], scores[0]):
        chunk = _STATE.as_chunk(int(idx), float(score))
        if chunk is not None:
            chunks.append(chunk)
    reranked = _rerank(query, chunks)
    return reranked[:k]


def _rerank(query: str, chunks: Iterable[Chunk]) -> List[Chunk]:
    reranked: List[Chunk] = []
    for chunk in chunks:
        boost = fuzz.partial_ratio(query, chunk.text[:1200]) / 100.0
        reranked.append(
            Chunk(
                doc_path=chunk.doc_path,
                shortname=chunk.shortname,
                chunk=chunk.chunk,
                text=chunk.text,
                snippet=chunk.snippet,
                score=chunk.score + (0.2 * boost),
            )
        )
    reranked.sort(key=lambda c: c.score, reverse=True)
    return reranked


def answer(query: str, k: int = 6, style: str = "concise") -> Dict[str, object]:
    query = query.strip()
    if not query:
        return {"text": "No strong match", "citations": [], "chunks": []}
    hits = search(query, k=k)
    if not hits:
        return {"text": "No strong match", "citations": [], "chunks": []}
    prompt = _build_prompt(query, hits, style)
    text = _synthesise(prompt)
    if not text:
        return {"text": "No strong match", "citations": [], "chunks": []}
    citations = _build_citations(hits)
    cleaned_text = text.strip()
    if citations:
        cleaned_text = _ensure_citations(cleaned_text, citations)
    return {"text": cleaned_text, "citations": citations, "chunks": hits}


def _build_prompt(query: str, chunks: List[Chunk], style: str) -> str:
    style_hint = _STYLE_HINTS.get(style, _STYLE_HINTS["concise"])
    context_lines = []
    for chunk in chunks:
        context_lines.append(f"{chunk.label}: {chunk.text}")
    context = "\n\n".join(context_lines)
    return (
        "You are an elite trading coach for Slum House Capital. "
        "Paraphrase insights from the provided context without quoting more than 90 continuous characters. "
        "Use the citation labels exactly as provided when you reference a source. "
        f"{style_hint}\n\n"
        f"Question: {query}\n"
        "Context:\n"
        f"{context}\n\n"
        "Answer:"
    )


def _synthesise(prompt: str) -> str:
    nemotron = _call_nemotron(prompt)
    if nemotron:
        return nemotron
    if OPENAI_API_KEY and OpenAI is not None:
        return _call_openai(prompt)
    return ""


def _call_nemotron(prompt: str) -> str:
    if not OLLAMA_URL:
        return ""
    try:
        response = requests.post(
            f"{OLLAMA_URL.rstrip('/')}/api/generate",
            json={"model": NEMOTRON_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
    except Exception as exc:  # pragma: no cover - network failures
        LOGGER.warning("Nemotron call failed: %s", exc)
        return ""


def _call_openai(prompt: str) -> str:
    if not OPENAI_API_KEY or OpenAI is None:
        return ""
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        result = client.responses.create(
            model=OPENAI_MODEL,
            input=prompt,
        )
        return (result.output_text or "").strip()
    except Exception as exc:  # pragma: no cover - network failures
        LOGGER.warning("OpenAI fallback failed: %s", exc)
        return ""


def _build_citations(chunks: Iterable[Chunk]) -> List[Dict[str, object]]:
    citations: List[Dict[str, object]] = []
    seen = set()
    for chunk in chunks:
        label = chunk.label
        if label in seen:
            continue
        seen.add(label)
        citations.append(
            {
                "doc": Path(chunk.doc_path).name,
                "shortname": chunk.shortname,
                "chunk": chunk.chunk,
                "label": label,
            }
        )
    return citations


def _ensure_citations(text: str, citations: List[Dict[str, object]]) -> str:
    labels = [item["label"] for item in citations]
    missing = [label for label in labels if label not in text]
    if missing:
        suffix = " Sources: " + ", ".join(missing)
        return f"{text}\n{suffix}" if "\n" in text else f"{text} {suffix}"
    return text


def compact_citation_labels(citations: Iterable[Dict[str, object]]) -> List[str]:
    labels = []
    seen = set()
    for citation in citations:
        label = citation.get("label")
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def format_source_line(citations: Iterable[Dict[str, object]]) -> str:
    labels = compact_citation_labels(citations)
    if not labels:
        return ""
    return "Sources: " + ", ".join(labels)
