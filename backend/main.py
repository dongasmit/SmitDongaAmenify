"""
FastAPI Application — Amenify AI Customer Support Bot
Serves the chat API and static frontend files.
"""

import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from backend.ingestion import build_knowledge_base, collection_exists
from backend.rag import generate_answer


# ── Session storage (in-memory) ──────────────────────────────────────────────
sessions: dict[str, list[dict]] = {}


# ── Lifespan: build knowledge base on startup ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the knowledge base on startup if it doesn't exist."""
    if not collection_exists():
        print("[SETUP] Building knowledge base on first startup...")
        try:
            build_knowledge_base()
        except Exception as e:
            print(f"[ERROR] Failed to build knowledge base: {e}")
            print("   Make sure GEMINI_API_KEY is set and knowledge_base.json exists.")
    else:
        print("[OK] Knowledge base already exists.")
    yield


# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Amenify AI Support Bot",
    description="AI-powered customer support chatbot for Amenify",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for development / hosted deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    response: str
    sources: list[str]
    session_id: str


class SessionResponse(BaseModel):
    session_id: str


# ── API Routes ───────────────────────────────────────────────────────────────
@app.post("/api/session", response_model=SessionResponse)
async def create_session():
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    sessions[session_id] = []
    return SessionResponse(session_id=session_id)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Process a chat message and return an AI response."""
    # Validate session
    if request.session_id not in sessions:
        sessions[request.session_id] = []

    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Get chat history for this session
    chat_history = sessions[request.session_id]

    try:
        # Generate response using RAG pipeline
        result = generate_answer(
            query=request.message.strip(),
            chat_history=chat_history,
        )

        # Store in session history
        sessions[request.session_id].append(
            {
                "user": request.message.strip(),
                "assistant": result["answer"],
            }
        )

        # Limit session history to last 20 exchanges
        if len(sessions[request.session_id]) > 20:
            sessions[request.session_id] = sessions[request.session_id][-20:]

        return ChatResponse(
            response=result["answer"],
            sources=result["sources"],
            session_id=request.session_id,
        )

    except Exception as e:
        print(f"Error processing chat: {e}")
        raise HTTPException(
            status_code=500,
            detail="Sorry, I encountered an error processing your request. Please try again.",
        )


@app.delete("/api/session/{session_id}")
async def clear_session(session_id: str):
    """Clear chat history for a session."""
    if session_id in sessions:
        sessions[session_id] = []
    return {"status": "cleared"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    kb_ready = collection_exists()
    return {
        "status": "healthy",
        "knowledge_base": "ready" if kb_ready else "not initialized",
        "active_sessions": len(sessions),
    }


# ── Serve frontend static files ─────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")


@app.get("/")
async def serve_frontend():
    """Serve the main HTML file."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(
        content={"message": "Frontend not found. API is running at /api/health"},
        status_code=200,
    )


# Mount static files (if any additional assets exist)
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
