"""
Script thử nghiệm độc lập cho RAG pipeline.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.rag.query_analyzer import analyze_query
from src.rag.hybrid_retriever import retrieve_candidates
from src.rag.reranker import rerank_documents
from src.rag.context_builder import build_context
from src.llm.client import invoke_llm
from src.prompts.answer_prompt import GROUNDED_ANSWER_PROMPT


def main():
    query = "Môn Hệ thống nhúng có bao nhiêu tín chỉ và ai phụ trách?"
    print(f"Query: {query}")

    analyzed = analyze_query(query)
    candidates = retrieve_candidates(analyzed, top_k=10)
    print(f"Retrieved {len(candidates)} candidates.")

    reranked = rerank_documents(query, candidates, top_k=5)
    print(f"Reranked {len(reranked)} documents.")

    context, sources = build_context(reranked, targets=analyzed.targets)
    print(f"Context length: {len(context)} chars, sources: {len(sources)}")

    prompt = GROUNDED_ANSWER_PROMPT.format(
        student_profile="Chưa có",
        context=context,
        question=query
    )
    answer = invoke_llm(prompt)
    print(f"\nCâu trả lời:\n{answer}")


if __name__ == "__main__":
    main()
