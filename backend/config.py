"""Configuration for the LLM Council."""

import os
from dotenv import load_dotenv

load_dotenv()

# OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL = "google/gemini-3-pro-preview"

# OpenRouter API endpoint
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Data directory for conversation storage
DATA_DIR = "data/conversations"

# RAG Configuration
RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"
VECTOR_DB_DIR = "data/vectordb"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # Fast, good quality
SEMANTIC_SIMILARITY_THRESHOLD = 0.98  # High threshold for semantic deduplication
CHUNK_SIZE = 200  # Target words per chunk (approximate)
TOP_K_RETRIEVAL = 10  # Number of chunks to retrieve
CONSENSUS_WEIGHT = 0.3  # Weight for consensus score in re-ranking (0.0-1.0)
