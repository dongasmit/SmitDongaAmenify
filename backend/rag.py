"""
RAG (Retrieval-Augmented Generation) Pipeline
Retrieves relevant context from ChromaDB and generates grounded answers using Google Gemini.
"""

import os
import google.generativeai as genai
from dotenv import load_dotenv
from backend.ingestion import get_chroma_client, get_embedding_function, COLLECTION_NAME

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Model configuration
CHAT_MODEL = "gemini-2.5-flash-lite"
TEMPERATURE = 0.0
MAX_TOKENS = 512
TOP_K = 5  # Number of chunks to retrieve

# System prompt that enforces grounded answers
SYSTEM_PROMPT = """You are a helpful customer support assistant for Amenify, a real-estate technology company that provides lifestyle services to apartment residents across the US.

STRICT RULES:
1. You must ONLY answer questions using the provided context from Amenify's knowledge base.
2. If the answer to a question is NOT found in the provided context, you MUST respond with: "I don't know. For more help, please contact our support team at concierge@amenify.com or call 719-767-1963 (available 7 days a week)."
3. Do NOT make up information, speculate, or use your general knowledge.
4. Be friendly, concise, and professional.
5. When listing services or features, use bullet points for clarity.
6. If asked about pricing specifics not in the context, direct users to the app or support team.
7. Always maintain a helpful and welcoming tone consistent with the Amenify brand.

CONTEXT FROM AMENIFY KNOWLEDGE BASE:
{context}"""


def retrieve(query: str, top_k: int = TOP_K) -> list[dict]:
    """
    Retrieve the most relevant chunks from the knowledge base.

    Args:
        query: The user's question.
        top_k: Number of chunks to retrieve.

    Returns:
        List of dicts with 'text', 'source_url', and 'page_name'.
    """
    chroma_client = get_chroma_client()
    embed_fn = get_embedding_function()

    collection = chroma_client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
    )

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    chunks = []
    if results and results["documents"]:
        for i, doc_text in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else None
            chunks.append(
                {
                    "text": doc_text,
                    "source_url": metadata.get("source_url", ""),
                    "page_name": metadata.get("page_name", ""),
                    "distance": distance,
                }
            )

    return chunks


def format_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context string for the prompt."""
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("page_name", "Unknown")
        context_parts.append(f"[Source: {source}]\n{chunk['text']}")
    return "\n\n---\n\n".join(context_parts)


def format_chat_history(history: list[dict]) -> list[dict]:
    """Format chat history into Gemini message format."""
    messages = []
    for entry in history[-6:]:  # Keep last 6 exchanges for context window
        messages.append({"role": "user", "parts": [entry["user"]]})
        messages.append({"role": "model", "parts": [entry["assistant"]]})
    return messages


def generate_answer(
    query: str,
    chat_history: list[dict] = None,
) -> dict:
    """
    Generate an answer using RAG: retrieve context, then generate with Gemini.

    Args:
        query: The user's question.
        chat_history: Previous conversation turns.

    Returns:
        Dict with 'answer', 'sources' (list of source URLs).
    """
    # Step 1: Retrieve relevant context
    chunks = retrieve(query)

    # Step 2: Format context
    context = format_context(chunks)

    # Step 3: Build the system instruction with context
    system_instruction = SYSTEM_PROMPT.format(context=context)

    # Step 4: Initialize Gemini model
    model = genai.GenerativeModel(
        model_name=CHAT_MODEL,
        system_instruction=system_instruction,
        generation_config=genai.GenerationConfig(
            temperature=TEMPERATURE,
            max_output_tokens=MAX_TOKENS,
        ),
    )

    # Step 5: Build conversation history + current query
    history = []
    if chat_history:
        history = format_chat_history(chat_history)

    # Start chat with history and send current message
    chat = model.start_chat(history=history)
    response = chat.send_message(query)

    answer = response.text.strip()

    # Collect unique source URLs
    sources = list(
        dict.fromkeys(
            chunk["source_url"] for chunk in chunks if chunk.get("source_url")
        )
    )

    return {
        "answer": answer,
        "sources": sources,
    }
