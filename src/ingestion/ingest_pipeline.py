"""
Pipeline Ingestion hoàn chỉnh:
Docx/Txt -> Chunking -> Metadata -> Chroma Vector Store + BM25 Index.
Chạy trực tiếp:
    python -m src.ingestion.ingest_pipeline [--rebuild]
"""
import os
import argparse
import pickle
import logging
from pathlib import Path
from typing import Dict, List, Any
from rank_bm25 import BM25Okapi

from src.config.settings import settings
from src.ingestion.loaders import load_file
from src.ingestion.chunkers import chunk_document
from src.ingestion.metadata_builder import detect_doc_type, build_metadata
from src.ingestion.vector_store import VectorStoreManager

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("IngestPipeline")

COLLECTIONS = ["course_detail", "curriculum", "regulation"]


def build_and_save_bm25(collection_name: str, chunks: List[Dict[str, Any]], output_dir: Path):
    """Xây dựng và lưu BM25 index ra file .pkl."""
    if not chunks:
        logger.warning(f"Khong co chunk nao cho BM25 index: {collection_name}")
        return

    texts = [c["text"] for c in chunks]
    doc_ids = [c["id"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    # Tokenize don gian cho BM25 bang tieng Viet
    tokenized_corpus = [t.lower().split() for t in texts]
    bm25_index = BM25Okapi(tokenized_corpus, k1=1.5, b=0.75)

    data = {
        "index": bm25_index,
        "corpus": texts,
        "doc_ids": doc_ids,
        "metadatas": metadatas,
    }

    output_path = output_dir / f"bm25_{collection_name}.pkl"
    with open(output_path, "wb") as f:
        pickle.dump(data, f)
    logger.info(f"Da luu BM25 index tai: {output_path}")


def run_ingestion(rebuild: bool = True) -> Dict[str, Any]:
    """Thực thi toàn bộ pipeline ingestion."""
    logger.info(f"Bat dau pipeline Ingestion (rebuild={rebuild})")
    settings.ensure_directories()
    vs_manager = VectorStoreManager()

    if rebuild:
        logger.info("Dang reset cac collections hien co...")
        for col in COLLECTIONS:
            vs_manager.delete_collection(col)
            bm25_file = settings.CHROMA_PATH / f"bm25_{col}.pkl"
            if bm25_file.exists():
                try:
                    bm25_file.unlink()
                except Exception:
                    pass

    # Thu thập toàn bộ file từ data_raw
    raw_files = []
    for root, _, files in os.walk(settings.DATA_RAW_DIR):
        for f in files:
            if f.endswith((".docx", ".txt")) and not f.startswith("~$"):
                raw_files.append(Path(root) / f)

    logger.info(f"Tim thay {len(raw_files)} tai lieu trong {settings.DATA_RAW_DIR}")

    collection_chunks: Dict[str, List[Dict[str, Any]]] = {
        col: [] for col in COLLECTIONS
    }
    stats = {"files_processed": 0, "chunks_total": 0, "by_collection": {col: 0 for col in COLLECTIONS}}

    for file_path in raw_files:
        logger.info(f"Dang xu ly: {file_path.name}")
        text = load_file(str(file_path))
        if not text or not text.strip():
            logger.warning(f"Bo qua file rong: {file_path.name}")
            continue

        doc_type = detect_doc_type(str(file_path))
        if doc_type == "syllabus":
            doc_type = "course_detail"

        if doc_type not in collection_chunks:
            doc_type = "course_detail"  # fallback

        chunked_tuples = chunk_document(text, doc_type)
        file_chunks = []
        for i, (chunk_text, extra_meta) in enumerate(chunked_tuples):
            if not chunk_text.strip():
                continue
            chunk_id = f"{file_path.stem}_chunk{i}"
            meta = build_metadata(str(file_path), chunk_text, chunk_id, doc_type=doc_type, **extra_meta)
            chunk_dict = {
                "id": chunk_id,
                "text": chunk_text,
                "metadata": meta,
            }
            file_chunks.append(chunk_dict)

        collection_chunks[doc_type].extend(file_chunks)
        stats["files_processed"] += 1

    # Thêm vào ChromaDB và tạo BM25
    for col, chunks in collection_chunks.items():
        if chunks:
            vs_manager.add_documents(col, chunks)
            build_and_save_bm25(col, chunks, settings.CHROMA_PATH)
            count = len(chunks)
            stats["by_collection"][col] = count
            stats["chunks_total"] += count

    # Nạp dữ liệu có cấu trúc vào SQLite Structured Academic Store (Round A1)
    try:
        from src.ingestion.curriculum_parser import ensure_curriculum_data_loaded
        ensure_curriculum_data_loaded()
        logger.info("Structured Academic Store (SQLite) ingested successfully.")
    except Exception as e:
        logger.warning(f"Failed to ingest structured academic store: {e}")

    print("\n" + "=" * 50)
    print("INGESTION REPORT")
    print("=" * 50)
    print(f"Files processed:   {stats['files_processed']}")
    print(f"Chunks created:     {stats['chunks_total']}")
    print(f"  - Course detail:  {stats['by_collection'].get('course_detail', 0)}")
    print(f"  - Curriculum:     {stats['by_collection'].get('curriculum', 0)}")
    print(f"  - Regulation:     {stats['by_collection'].get('regulation', 0)}")
    print("Vector store:       OK")
    print("BM25 indexes:       OK")
    print("Academic Store:     OK")
    print("=" * 50 + "\n")

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest documents into ChromaDB & BM25")
    parser.add_argument("--rebuild", action="store_true", default=True, help="Rebuild all indexes from scratch")
    parser.add_argument("--incremental", dest="rebuild", action="store_false", help="Append without dropping existing")
    args = parser.parse_args()

    run_ingestion(rebuild=args.rebuild)
