"""Standalone script to index PDFs into ChromaDB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag import get_collection, ingest_pdfs


def main():
    print("Starting PDF ingestion...")
    n = ingest_pdfs()
    total = get_collection().count()
    print(f"\nDone. Indexed {n} new document(s). Total chunks in DB: {total}")


if __name__ == "__main__":
    main()
