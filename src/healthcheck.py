"""
CLI Healthcheck Script: Kiểm tra tình trạng sẵn sàng hoạt động của AI Academic Advisor.
Thực thi: python -m src.healthcheck
"""
import sys
import logging

from src.config.settings import settings
from src.ingestion.vector_store import get_chroma_client
from src.llm.client import is_live_llm_ready

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("healthcheck")


def run_healthcheck() -> bool:
    print("\n========================================================")
    print("      AI ACADEMIC ADVISOR - SYSTEM HEALTH CHECK         ")
    print("========================================================")

    all_ok = True

    # 1. Kiểm tra Runtime Directory
    runtime_ok = settings.RUNTIME_DIR.exists()
    print(f"[*] Runtime Directory ({settings.RUNTIME_DIR}): {'OK' if runtime_ok else 'CREATED'}")
    if not runtime_ok:
        settings.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Kiểm tra Vector Store (ChromaDB)
    chroma_dir_ok = settings.CHROMA_PATH.exists()
    print(f"[*] ChromaDB Directory ({settings.CHROMA_PATH}): {'OK' if chroma_dir_ok else 'MISSING'}")
    if not chroma_dir_ok:
        all_ok = False

    # 3. Kiểm tra ChromaDB Collections & Counts
    collections = ["course_detail", "curriculum", "regulation"]
    total_docs = 0
    try:
        client = get_chroma_client()
        for col_name in collections:
            col = client.get_collection(col_name)
            count = col.count()
            total_docs += count
            status = "OK" if count > 0 else "EMPTY (Run Ingestion!)"
            print(f"    - Collection '{col_name}': {count} vectors [{status}]")
            if count == 0:
                all_ok = False
    except Exception as e:
        print(f"    [!] Error checking ChromaDB collections: {e}")
        all_ok = False

    # 4. Kiểm tra BM25 Indexes
    bm25_missing = []
    for col_name in collections:
        bm25_file = settings.CHROMA_PATH / f"bm25_{col_name}.pkl"
        if not bm25_file.exists():
            bm25_missing.append(bm25_file.name)

    if not bm25_missing:
        print("[*] BM25 Indexes (3/3 files found): OK")
    else:
        print(f"[*] BM25 Indexes: MISSING ({', '.join(bm25_missing)})")
        all_ok = False

    # 5. Kiểm tra LLM Configuration
    live_ready = is_live_llm_ready()
    key_masked = f"{settings.LLM_API_KEY[:6]}...{settings.LLM_API_KEY[-4:]}" if len(settings.LLM_API_KEY) > 10 else "NOT_CONFIGURED"
    print(f"[*] LLM Provider: {settings.LLM_PROVIDER} | Model: {settings.LLM_MODEL}")
    print(f"    - Base URL: {settings.LLM_BASE_URL}")
    print(f"    - API Key: {key_masked}")
    print(f"    - Status: {'READY (Live API)' if live_ready else 'MOCK / OFFLINE MODE'}")

    # 6. Kiểm tra Reranker
    print(f"[*] Cross-Encoder Reranker: {'ENABLED (' + settings.RERANKER_MODEL + ')' if settings.ENABLE_RERANKER else 'DISABLED (Fast RRF hybrid fallback)'}")

    # 7. Kiểm tra Email Sender
    print(f"[*] Email Service: {'ENABLED (' + settings.SMTP_HOST + ')' if settings.EMAIL_ENABLED else 'DISABLED (Safe simulated mode)'}")

    # 8. Kiểm tra Web Frontend Static Assets
    fe_index = settings.FRONTEND_DIR / "index.html"
    fe_css = settings.FRONTEND_DIR / "css" / "style.css"
    fe_js = settings.FRONTEND_DIR / "js" / "app.js"
    fe_ok = fe_index.exists() and fe_css.exists() and fe_js.exists()
    print(f"[*] Frontend Assets ({settings.FRONTEND_DIR}): {'OK' if fe_ok else 'MISSING ASSETS'}")
    if not fe_ok:
        all_ok = False

    print("========================================================")
    if all_ok:
        print(">>> SYSTEM STATUS: HEALTHY & READY TO SERVE <<<")
    else:
        print(">>> SYSTEM STATUS: WARNING (Ingest raw data or configure settings) <<<")
    print("========================================================\n")

    return all_ok


def main():
    healthy = run_healthcheck()
    sys.exit(0 if healthy else 1)


if __name__ == "__main__":
    main()
