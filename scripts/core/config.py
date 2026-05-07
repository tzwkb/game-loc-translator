"""
config.py — Global configuration for game-loc-translator.
Modify this file to switch API providers, models, and paths.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR   = Path(__file__).parent.parent.parent
INPUT_DIR  = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
WORKSPACE_DIR = BASE_DIR / "workspace"
LOG_DIR    = BASE_DIR / "logs"
PROMPTS_DIR = BASE_DIR / "prompts"

for d in [INPUT_DIR, OUTPUT_DIR, WORKSPACE_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# API Configuration
# ---------------------------------------------------------------------------
API_BASE_URL = os.environ.get("GAME_LOC_API_BASE", "https://api.vectorengine.ai/v1")
API_KEY      = os.environ.get("GAME_LOC_API_KEY", "")

# Unified model for all batches
MODEL = "gemini-3.1-pro-preview"

MAX_TOKENS   = 8192
TEMPERATURE  = 0.3
REQUEST_TIMEOUT = 300
MAX_RETRIES  = 5
RETRY_DELAY  = 5
MAX_WORKERS  = 100

# ---------------------------------------------------------------------------
# Batch Settings
# ---------------------------------------------------------------------------
BATCH_SIZE = 1  # rows per API call (single-row mode to avoid token truncation)

# ---------------------------------------------------------------------------
# RAG / Corpus Settings
# ---------------------------------------------------------------------------
PROJECT_PROFILES  = BASE_DIR / "project_profiles.json"
CORPUS_DB_PATH    = WORKSPACE_DIR / "corpus.db"
CORPUS_FAISS_PATH = WORKSPACE_DIR / "corpus.faiss"
EMBEDDING_MODEL   = "BAAI/bge-m3"  # 1024 dim, multilingual
VECTOR_DIM        = 1024
RAG_TOP_K         = 3
RAG_SIM_THRESHOLD = 0.65

# ---------------------------------------------------------------------------
# Output Settings
# ---------------------------------------------------------------------------
OUTPUT_SUFFIX = "_translated"
OUTPUT_COLUMN_HEADER = "Translation"
