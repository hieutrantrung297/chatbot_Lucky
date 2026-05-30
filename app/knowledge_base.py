"""RAG knowledge base — ChromaDB + multilingual sentence-transformers."""

import logging
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

logger = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge"
_CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma_db"

_embed_fn = None
_collection = None


def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
    return _embed_fn


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
        _collection = client.get_or_create_collection(
            name="lucky_knowledge",
            embedding_function=_get_embed_fn(),
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _chunk_text(text: str, source: str) -> list[dict]:
    """Split text into paragraph-level chunks, filter trivially short ones."""
    chunks = []
    for i, block in enumerate(text.split("\n\n")):
        block = block.strip()
        if len(block) > 30:
            chunks.append({"id": f"{source}_{i}", "text": block, "source": source})
    return chunks


def build_index() -> None:
    """Build (or rebuild) the ChromaDB index from knowledge markdown files."""
    col = _get_collection()

    chunks: list[dict] = []

    for md_file in sorted(_KNOWLEDGE_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        chunks.extend(_chunk_text(text, md_file.stem))

    if not chunks:
        logger.warning("Không có document nào để index")
        return

    existing = col.get()
    if existing["ids"]:
        col.delete(ids=existing["ids"])

    col.add(
        documents=[c["text"] for c in chunks],
        ids=[c["id"] for c in chunks],
        metadatas=[{"source": c["source"]} for c in chunks],
    )
    logger.info("Knowledge base: đã index %d chunks", len(chunks))


def search(query: str, n_results: int = 4) -> str:
    """Semantic search — trả về context dạng text để inject vào LLM."""
    try:
        col = _get_collection()
        count = col.count()
        if count == 0:
            return "Chưa có dữ liệu trong knowledge base."

        results = col.query(
            query_texts=[query],
            n_results=min(n_results, count),
        )
        docs = [d for d in results["documents"][0] if d is not None]
        if not docs:
            return "Không tìm thấy thông tin liên quan."

        return "\n\n---\n\n".join(docs)
    except Exception as exc:
        logger.error("KB search error: %s", exc)
        return "Lỗi tìm kiếm thông tin."
