from pathlib import Path
from typing import List
import chromadb
from sentence_transformers import SentenceTransformer
import pdfplumber
from app.config import get_config

DATA_DIR = Path(__file__).parent.parent / "data" / "chroma"
RAW_DIR = Path(__file__).parent.parent / "raw"

_embedder: SentenceTransformer = None
_collection = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        model = get_config()["embedding"]["model"]
        _embedder = SentenceTransformer(model)
    return _embedder


def get_collection():
    global _collection
    if _collection is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(DATA_DIR))
        _collection = client.get_or_create_collection("wiki_docs")
    return _collection


def _chunk(text: str, size: int, overlap: int) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunk = text[start : start + size]
        if len(chunk.strip()) > 50:
            chunks.append(chunk)
        start += size - overlap
    return chunks


def ingest_pdfs() -> int:
    cfg = get_config()["retrieval"]
    collection = get_collection()
    embedder = _get_embedder()
    ingested = 0

    for pdf_path in sorted(RAW_DIR.glob("*.pdf")):
        doc_id = pdf_path.stem
        existing = collection.get(where={"source": doc_id}, limit=1)
        if existing["ids"]:
            print(f"Already indexed: {pdf_path.name}")
            continue

        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception as e:
            print(f"Error reading {pdf_path.name}: {e}")
            continue

        chunks = _chunk(text, cfg["chunk_size"], cfg["chunk_overlap"])
        if not chunks:
            continue

        embeddings = embedder.encode(chunks, show_progress_bar=False).tolist()
        ids = [f"{doc_id}__{i}" for i in range(len(chunks))]
        metadatas = [{"source": doc_id, "chunk_idx": i} for i in range(len(chunks))]

        collection.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
        ingested += 1
        print(f"Indexed: {pdf_path.name} ({len(chunks)} chunks)")

    return ingested


def search(query: str, top_k: int = None) -> List[dict]:
    cfg = get_config()
    if top_k is None:
        top_k = cfg["retrieval"]["top_k"]

    collection = get_collection()
    total = collection.count()
    if total == 0:
        return []

    embedder = _get_embedder()
    q_emb = embedder.encode([query]).tolist()

    results = collection.query(
        query_embeddings=q_emb,
        n_results=min(top_k, total),
        include=["documents", "metadatas", "distances"],
    )

    docs = []
    for i, doc in enumerate(results["documents"][0]):
        docs.append(
            {
                "content": doc,
                "source": results["metadatas"][0][i]["source"],
                "score": round(1 - results["distances"][0][i], 3),
            }
        )
    return docs
