from rag.hybrid_retriever import hybrid_retrieve


def search_documents(question):

    docs = hybrid_retrieve(question)

    return docs