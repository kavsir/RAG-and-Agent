"""
Convenience entrypoint delegating to ingest_pipeline.
"""
from src.ingestion.ingest_pipeline import run_ingestion

if __name__ == "__main__":
    run_ingestion(rebuild=True)
