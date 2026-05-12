# check_vector.py

import chromadb

client = chromadb.PersistentClient(path="vector_store")

collections = client.list_collections()

for c in collections:

    col = client.get_collection(c.name)

    print(c.name, ":", col.count())