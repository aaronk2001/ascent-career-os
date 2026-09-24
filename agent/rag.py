"""
Linda RAG memory store — local ChromaDB with sentence-transformers embeddings.

This is the "learning loop" for Linda: a persistent vector store at
career-planner/data/linda_rag/ that grows as the user works with the assistant.

Two write modes:
  - explicit `remember(text, tag)` from a Linda tool call
  - bulk `ingest_corpus()` from any markdown files in data/linda_corpus/

Both backends are fail-soft: if `chromadb` isn't installed the module
exposes stub functions that report the missing dependency cleanly.
The agent loop never crashes from RAG being unavailable.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
RAG_DIR = ROOT / "data" / "linda_rag"
CORPUS_DIR = ROOT / "data" / "linda_corpus"
COLLECTION_NAME = "linda_career"

# Lazy singletons — initialized on first call
_client = None
_collection = None


def _import_chroma():
    """Return (chromadb, embedding_fn) or (None, None) if unavailable."""
    try:
        import chromadb  # type: ignore
        from chromadb.utils import embedding_functions  # type: ignore
        return chromadb, embedding_functions
    except ImportError as exc:
        log.info("chromadb not installed; RAG disabled: %s", exc)
        return None, None


def _get_collection():
    """Return the ChromaDB collection, creating it if needed.

    Returns None if chromadb isn't installed — callers must handle that.
    """
    global _client, _collection
    if _collection is not None:
        return _collection

    chromadb, embedding_functions = _import_chroma()
    if chromadb is None:
        return None

    RAG_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(RAG_DIR))

    # Default sentence-transformers all-MiniLM-L6-v2 — small + good enough
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    _collection = _client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"created": datetime.now(timezone.utc).isoformat()},
    )
    return _collection


# ── public API used by tools.py ────────────────────────────────────────────────

def remember(text: str, tag: str = "general") -> dict:
    """Store a snippet. Returns {success, id, count} or {success: False, error}."""
    if not text or not text.strip():
        return {"success": False, "error": "text is empty"}

    coll = _get_collection()
    if coll is None:
        return {
            "success": False,
            "error": "chromadb not installed. `pip install chromadb sentence-transformers`",
        }

    try:
        doc_id = f"mem_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        coll.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[{
                "tag": tag,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "source": "explicit",
            }],
        )
        return {"success": True, "id": doc_id, "count": coll.count()}
    except Exception as exc:
        log.error("RAG remember failed: %s", exc)
        return {"success": False, "error": str(exc)}


def search(query: str, k: int = 5, tag_filter: str | None = None) -> dict:
    """Return top-k snippets matching the query."""
    if not query or not query.strip():
        return {"success": False, "error": "query is empty"}

    coll = _get_collection()
    if coll is None:
        return {
            "success": False,
            "error": "chromadb not installed. `pip install chromadb sentence-transformers`",
        }

    try:
        where = {"tag": tag_filter} if tag_filter else None
        result = coll.query(query_texts=[query], n_results=min(int(k), 10), where=where)
        hits = []
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for i, doc in enumerate(docs):
            hits.append({
                "text": doc,
                "tag": (metas[i] or {}).get("tag") if i < len(metas) else None,
                "source": (metas[i] or {}).get("source") if i < len(metas) else None,
                "distance": dists[i] if i < len(dists) else None,
            })
        return {"success": True, "hits": hits, "total_in_store": coll.count()}
    except Exception as exc:
        log.error("RAG search failed: %s", exc)
        return {"success": False, "error": str(exc)}


def ingest_corpus() -> dict:
    """Ingest every .md file under data/linda_corpus/ as RAG documents.

    Idempotent: re-ingesting overwrites previous entries with the same
    file-derived id. Safe to call on every app boot.
    """
    coll = _get_collection()
    if coll is None:
        return {"success": False, "error": "chromadb not installed"}

    if not CORPUS_DIR.exists():
        return {"success": True, "ingested": 0, "note": f"{CORPUS_DIR} does not exist yet"}

    md_files = sorted(CORPUS_DIR.rglob("*.md"))
    if not md_files:
        return {"success": True, "ingested": 0, "note": "no .md files in corpus"}

    ingested = 0
    errors = []
    for md in md_files:
        try:
            text = md.read_text(encoding="utf-8")
            if not text.strip():
                continue
            doc_id = f"corpus_{md.relative_to(CORPUS_DIR).as_posix()}"
            coll.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[{
                    "tag": "corpus",
                    "source": str(md.relative_to(CORPUS_DIR)),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }],
            )
            ingested += 1
        except Exception as exc:
            errors.append({"file": str(md), "error": str(exc)})

    return {
        "success": True,
        "ingested": ingested,
        "errors": errors,
        "total_in_store": coll.count(),
    }


def stats() -> dict:
    """Diagnostic — count, location, ingest readiness."""
    coll = _get_collection()
    if coll is None:
        return {"available": False, "reason": "chromadb not installed"}
    return {
        "available": True,
        "rag_dir": str(RAG_DIR),
        "corpus_dir": str(CORPUS_DIR),
        "doc_count": coll.count(),
        "collection_name": COLLECTION_NAME,
    }
