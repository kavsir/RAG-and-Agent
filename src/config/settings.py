import os
from pathlib import Path
from dotenv import load_dotenv

# Tìm và load .env từ thư mục gốc dự án
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BASE_DIR / ".env"
if _ENV_FILE.exists():
    load_dotenv(dotenv_path=_ENV_FILE)
else:
    load_dotenv()


class Settings:
    """Cấu hình tập trung cho toàn bộ ứng dụng."""

    # Base Directories
    BASE_DIR: Path = _BASE_DIR
    DATA_RAW_DIR: Path = _BASE_DIR / "data_raw"
    RUNTIME_DIR: Path = _BASE_DIR / "runtime"
    FRONTEND_DIR: Path = _BASE_DIR / "frontend"

    # LLM Provider Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower()
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "").strip()
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "30"))

    # Embeddings & Vector Database
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    CHROMA_PATH: Path = _BASE_DIR / os.getenv("CHROMA_PATH", "vector_store")

    # Retrieval Configuration
    RETRIEVAL_CANDIDATES: int = int(os.getenv("RETRIEVAL_CANDIDATES", "20"))
    RERANK_TOP_K: int = int(os.getenv("RERANK_TOP_K", "8"))
    CONTEXT_TOP_K: int = int(os.getenv("CONTEXT_TOP_K", "6"))
    MINIMUM_SCORE: float = float(os.getenv("MINIMUM_SCORE", "0.1"))
    ENABLE_RERANKER: bool = os.getenv("ENABLE_RERANKER", "true").lower() in ("true", "1", "yes")
    RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    # Server Configuration
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    # Optional Email Notification
    EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "false").lower() in ("true", "1", "yes")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")

    @classmethod
    def ensure_directories(cls):
        """Đảm bảo các thư mục cần thiết tồn tại."""
        cls.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        cls.CHROMA_PATH.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
