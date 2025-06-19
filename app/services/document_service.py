from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
import os
from openai import AzureOpenAI
from azure.search.documents.models import VectorizedQuery

import json
import requests

# For embedding model
EMBEDDING_MODEL_ENDPOINT= os.environ["EMBEDDING_MODEL_ENDPOINT"]
EMBEDDING_MODEL_KEY= os.environ["EMBEDDING_MODEL_KEY"]

# For actual searching
AZURE_SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
AZURE_SEARCH_INDEX=os.environ["AZURE_SEARCH_INDEX"]
AZURE_SEARCH_KEY=os.environ["AZURE_SEARCH_KEY"]

# don't be dumb remember this is for the embedding model not for chat
openai_client = AzureOpenAI(
    api_key= EMBEDDING_MODEL_KEY,
    azure_endpoint = EMBEDDING_MODEL_ENDPOINT,
    api_version="2023-05-15",
)

# client for azure ai search
search_client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT,
                             index_name=AZURE_SEARCH_INDEX,
                             credential=AzureKeyCredential(AZURE_SEARCH_KEY))

# Take string as parameter, return embedding
def generate_and_upload_chunks(extracted_text, user_id, filename):
    try: 
        chunks = [extracted_text[i:i+1000] for i in range(0, len(extracted_text), 1000)]
        # response = openai_client.embeddings.create(
        #     input=chunks,
        #     model="text-embedding-ada-002"
        # )

        # embeddings = []
        # for i, chunk in enumerate(chunks):
        #     embeddings.append({
        #         "text": chunk,
        #         "embedding": response.data[i].embedding
        #     })

        upload_documents(chunks, user_id, filename)

    except Exception as e: 
        return "Error: " + str(e)

    

# Test embedding model
# generate_embeddings("A hedge fund is a type of pooled investment fund that uses various sophisticated investment strategies to achieve high returns")

# upload to index
def upload_documents(text_chunks, user_id, filename):
    docs = []
    for idx, chunk in enumerate(text_chunks):
        docs.append({
            "id": f"{user_id}-{idx}",
            "user_id": user_id,
            "text": chunk,
            "source": filename
        })
        search_client.upload_documents(documents=docs)


# Vector Search
def vector_search(query_embedding, user_id, top_k=5):
    vector_query = VectorizedQuery(
        vector=query_embedding,
        k_nearest_neighbors=top_k,
        fields="embedding"
    )

    results = search_client.search(
        search_text="", 
        vector_queries=[vector_query],
        filter=f"user_id eq '{user_id}'",
        select=["text"]
    )

    return [doc["text"] for doc in results]