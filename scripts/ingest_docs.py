#!/usr/bin/env python3
"""Build or refresh the FAISS knowledge index for SHC agents."""
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import faiss
import numpy as np
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_ROOT = BASE_DIR / "knowledge" / "market"
INDEX_DIR = BASE_DIR / "data" / "index"
META_PATH = INDEX_DIR / "meta.json"
INDEX_PATH = INDEX_DIR / "index.faiss"
MODEL_NAME = os.getenv("SHC_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

logger = logging.getLogger("ingest")


@dataclass
class DocumentChunk:
    """Represent a chunk of text extracted from a PDF."""

    doc_path: str
    shortname: str
    chunk: int
    text: str
    snippet: str
    token_count: int

    def to_meta(self) -> Dict[str, object]:
        return {
            "doc_path": self.doc_path,
            "shortname": self.shortname,
            "chunk": self.chunk,
            "text": self.text,
            "snippet": self.snippet,
            "tokens": self.token_count,
        }


def load_existing_meta() -> Dict[str, object]:
    if not META_PATH.exists():
        return {}
    try:
        with META_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse existing metadata: %s", exc)
        return {}


def iter_pdfs(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    for path in sorted(root.rglob("*.pdf")):
        if path.is_file():
            yield path


def sanitize_shortname(path: Path) -> str:
    stem = path.stem.strip() or "document"
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in stem)
    cleaned = "_".join(filter(None, cleaned.split("_")))
    return cleaned or "document"


def extract_text(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: List[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if page_text:
            parts.append(page_text)
    return "\n\n".join(parts)


def chunk_text(text: str, *, chunk_tokens: int = 1100, overlap: int = 100) -> List[str]:
    words = text.split()
    if not words:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + chunk_tokens)
        chunk_words = words[start:end]
        if not chunk_words:
            break
        chunk = " ".join(chunk_words).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = end - overlap
    return chunks


def summarize_snippet(text: str, *, limit: int = 240) -> str:
    squished = " ".join(text.split())
    if len(squished) <= limit:
        return squished
    return squished[: limit - 1].rstrip() + "…"


def reuse_chunks_if_possible(
    path: Path, existing_meta: Dict[str, object]
) -> List[DocumentChunk] | None:
    doc_key = str(path)
    file_meta = existing_meta.get("files", {}).get(doc_key)
    if not file_meta:
        return None
    stat = path.stat()
    if file_meta.get("size") != stat.st_size:
        return None
    if int(file_meta.get("mtime", 0)) != int(stat.st_mtime):
        return None
    stored_chunks = [
        chunk for chunk in existing_meta.get("chunks", []) if chunk.get("doc_path") == doc_key
    ]
    if not stored_chunks:
        return None
    restored: List[DocumentChunk] = []
    for chunk in sorted(stored_chunks, key=lambda c: c["chunk"]):
        restored.append(
            DocumentChunk(
                doc_path=doc_key,
                shortname=chunk.get("shortname", sanitize_shortname(path)),
                chunk=int(chunk["chunk"]),
                text=chunk.get("text", ""),
                snippet=chunk.get("snippet", ""),
                token_count=int(chunk.get("tokens", len(chunk.get("text", "").split()))),
            )
        )
    return restored


def build_chunks(existing_meta: Dict[str, object]) -> List[DocumentChunk]:
    chunks: List[DocumentChunk] = []
    for pdf_path in iter_pdfs(PDF_ROOT):
        doc_key = str(pdf_path)
        reused = reuse_chunks_if_possible(pdf_path, existing_meta)
        if reused is not None:
            logger.info("Reusing cached chunks for %s", pdf_path)
            chunks.extend(reused)
            continue
        logger.info("Extracting %s", pdf_path)
        raw_text = extract_text(pdf_path)
        sections = chunk_text(raw_text)
        shortname = sanitize_shortname(pdf_path)
        for idx, section in enumerate(sections):
            if not section.strip():
                continue
            snippet = summarize_snippet(section)
            chunks.append(
                DocumentChunk(
                    doc_path=doc_key,
                    shortname=shortname,
                    chunk=idx,
                    text=section,
                    snippet=snippet,
                    token_count=len(section.split()),
                )
            )
    return chunks


def encode_chunks(model: SentenceTransformer, chunks: Sequence[DocumentChunk]) -> np.ndarray:
    texts = [chunk.text for chunk in chunks]
    if not texts:
        return np.zeros((0, model.get_sentence_embedding_dimension()), dtype="float32")
    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        show_progress_bar=len(texts) >= 5,
        normalize_embeddings=True,
    )
    if embeddings.dtype != np.float32:
        embeddings = embeddings.astype("float32")
    return embeddings


def save_index(embeddings: np.ndarray) -> None:
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    if embeddings.size:
        index.add(embeddings)
    faiss.write_index(index, str(INDEX_PATH))


def build_metadata(chunks: Sequence[DocumentChunk]) -> Dict[str, object]:
    files: Dict[str, Dict[str, object]] = {}
    for chunk in chunks:
        files.setdefault(chunk.doc_path, {})
    for doc_path in list(files.keys()):
        stat = Path(doc_path).stat()
        files[doc_path] = {
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
        }
    payload = {
        "model": MODEL_NAME,
        "updated": datetime.now(timezone.utc).isoformat(),
        "files": files,
        "chunks": [chunk.to_meta() for chunk in chunks],
    }
    return payload


def persist_metadata(payload: Dict[str, object]) -> None:
    with META_PATH.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def ingest() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    PDF_ROOT.mkdir(parents=True, exist_ok=True)

    existing_meta = load_existing_meta()

    chunks = build_chunks(existing_meta)
    if not chunks:
        logger.warning("No PDF chunks found under %s", PDF_ROOT)
        if INDEX_PATH.exists():
            INDEX_PATH.unlink()
        persist_metadata(
            {
                "model": MODEL_NAME,
                "updated": datetime.now(timezone.utc).isoformat(),
                "files": {},
                "chunks": [],
            }
        )
        return

    logger.info("Encoding %d chunks", len(chunks))
    model = SentenceTransformer(MODEL_NAME)
    embeddings = encode_chunks(model, chunks)
    logger.info("Building FAISS index with dim=%d", embeddings.shape[1])
    save_index(embeddings)
    metadata = build_metadata(chunks)
    persist_metadata(metadata)
    logger.info("Index updated at %s", INDEX_PATH)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest SHC knowledge PDFs into FAISS index")
    parser.parse_args(argv)
    ingest()


if __name__ == "__main__":
    main()
