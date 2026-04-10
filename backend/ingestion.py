"""
Knowledge Base Ingestion Pipeline
Chunks scraped documents, generates embeddings via Gemini, and stores in ChromaDB.
"""

import os
import json
import chromadb
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

# Configuration
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
COLLECTION_NAME = "amenify_knowledge"
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
KNOWLEDGE_BASE_PATH = os.path.join(os.path.dirname(__file__), "knowledge_base.json")


def get_chroma_client():
    """Get a persistent ChromaDB client."""
    return chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)


def get_embedding_function():
    """Get Google Gemini embedding function for ChromaDB."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    return embedding_functions.GoogleGenerativeAiEmbeddingFunction(
        api_key=api_key,
        model_name="models/gemini-embedding-001",
    )


def chunk_documents(documents: list[dict]) -> list[dict]:
    """
    Split documents into smaller chunks for embedding.

    Each chunk retains metadata (source URL, page name) for attribution.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for doc in documents:
        text_chunks = splitter.split_text(doc["content"])
        for i, chunk_text in enumerate(text_chunks):
            chunks.append(
                {
                    "id": f"{doc['page_name'].lower().replace(' ', '_')}_{i}",
                    "text": chunk_text,
                    "metadata": {
                        "source_url": doc["url"],
                        "page_name": doc["page_name"],
                        "chunk_index": i,
                    },
                }
            )

    return chunks


def build_knowledge_base(documents: list[dict] = None) -> int:
    """
    Build the vector knowledge base from documents.

    Args:
        documents: List of document dicts. If None, loads from knowledge_base.json.

    Returns:
        Number of chunks stored.
    """
    # Load documents if not provided
    if documents is None:
        if not os.path.exists(KNOWLEDGE_BASE_PATH):
            raise FileNotFoundError(
                f"Knowledge base file not found at {KNOWLEDGE_BASE_PATH}. "
                "Run the scraper first: python -m backend.scraper"
            )
        with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
            documents = json.load(f)

    print(f"[INFO] Processing {len(documents)} documents...")

    # Chunk documents
    chunks = chunk_documents(documents)
    print(f"[INFO] Created {len(chunks)} chunks")

    # Initialize ChromaDB
    client = get_chroma_client()
    embed_fn = get_embedding_function()

    # Delete existing collection if it exists, then recreate
    try:
        client.delete_collection(COLLECTION_NAME)
        print("[INFO] Cleared existing collection")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # Add chunks in batches
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        collection.add(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )
        print(f"  [+] Added batch {i // batch_size + 1}/{(len(chunks) - 1) // batch_size + 1}")

    print(f"[DONE] Knowledge base built with {len(chunks)} chunks")
    return len(chunks)


def collection_exists() -> bool:
    """Check if the ChromaDB collection exists and has data."""
    try:
        client = get_chroma_client()
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=get_embedding_function(),
        )
        return collection.count() > 0
    except Exception:
        return False


if __name__ == "__main__":
    build_knowledge_base()
