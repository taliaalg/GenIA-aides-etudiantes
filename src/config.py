"""Configuration centrale, lue depuis .env (voir .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CORPUS_DIR = ROOT / "data" / "corpus"
TESTS_FILE = ROOT / "data" / "tests.jsonl"
RESULTS_DIR = ROOT / "results"
LOGS_DIR = ROOT / "logs"

# LLM : n'importe quelle API compatible OpenAI (Ollama, Groq, Mistral, OpenAI...)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# Recherche
RETRIEVER = os.getenv("RETRIEVER", "hybrid")  # "hybrid" (dense + BM25) ou "bm25"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
TOP_K = int(os.getenv("TOP_K", "5"))

# Agent : boucle bornée
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))
AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "12000"))
