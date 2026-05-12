from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
import uuid


class VectorMemory:

    def __init__(self):

        self.client = PersistentClient(path="D:/Agent_AI_Levelup/Agent_AI_Levelup/src/memory/vector_memory")

        self.collection = self.client.get_or_create_collection(
            name="chat_memory"
        )

        # dùng cùng model với RAG
        self.embed_model = SentenceTransformer("BAAI/bge-m3")

    def add_memory(self, text):

        embedding = self.embed_model.encode(text).tolist()

        self.collection.add(
            documents=[text],
            embeddings=[embedding],
            ids=[str(uuid.uuid4())]
        )

    def search_memory(self, query, k=3):

        embedding = self.embed_model.encode(query).tolist()

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=k
        )

        return results["documents"][0]