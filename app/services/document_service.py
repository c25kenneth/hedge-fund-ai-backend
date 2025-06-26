from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
import os
from openai import AzureOpenAI
from azure.search.documents.models import VectorizedQuery
from datetime import datetime
from azure.storage.blob import BlobServiceClient, ContentSettings
import uuid
import json
import requests

# For embedding model
EMBEDDING_MODEL_ENDPOINT= os.environ["EMBEDDING_MODEL_ENDPOINT"]
EMBEDDING_MODEL_KEY= os.environ["EMBEDDING_MODEL_KEY"]

# For actual searching
AZURE_SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
AZURE_SEARCH_INDEX=os.environ["AZURE_SEARCH_INDEX"]
AZURE_SEARCH_KEY=os.environ["AZURE_SEARCH_KEY"]

# For Azure Blob Storage
BLOB_CONTAINER_NAME = os.environ["AZURE_BLOB_CONTAINER"]
BLOB_ACCESS_KEY = os.environ["AZURE_BLOB_ACCESS_KEY"]
BLOB_ACCOUNT_URL = os.environ["AZURE_BLOB_ACCOUNT_URL"]
blob_service_client = BlobServiceClient(account_url=BLOB_ACCOUNT_URL, credential=BLOB_ACCESS_KEY)

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

# Blob Functions
def generate_unique_filename(user_id, original_filename):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_id = uuid.uuid4().hex[:6]
    return f"{user_id}_{timestamp}_{unique_id}_{original_filename}"

def upload_file_to_blob(file, unique_filename):
    try:            
        print("Uploading file to blob")
        blob_client = blob_service_client.get_blob_client(
            container=BLOB_CONTAINER_NAME, blob=unique_filename
        )

        file.seek(0)

        blob_client.upload_blob(
            file,
            overwrite=True,
            content_settings=ContentSettings(content_type='application/pdf')
        )
        print("Blob upload complete")
        return blob_client.url
    
    except Exception as e:
        return "Error: " + str(e)

# Take string as parameter, return embedding
def generate_and_upload_chunks(file, user_id, filename, pages):
    try: 
        upload_documents(file, user_id, filename, pages)

    except Exception as e: 
        return "Error: " + str(e)

    

# Test embedding model
# generate_embeddings("A hedge fund is a type of pooled investment fund that uses various sophisticated investment strategies to achieve high returns")

# upload to index
def upload_documents(file, user_id, original_filename, pages):
    print("Uploading documents to index")
    unique_filename = generate_unique_filename(user_id, original_filename)
    blob_url = upload_file_to_blob(file, unique_filename)
    docs = []
    file.seek(0)
    try:
        for page_num, page in enumerate(pages):
            page_width = getattr(page, "width", None)
            page_height = getattr(page, "height", None)
            for line in page.lines:
                chunk_text = line.content
                polygon = [coord for point in line.polygon for coord in (point.x, point.y)]

                docs.append({
                    "id": f"{user_id}-{uuid.uuid4().hex[:8]}",
                    "user_id": user_id,
                    "text": chunk_text,
                    "source": original_filename,
                    "blob_url": blob_url,
                    "unique_filename": unique_filename,
                    "page_number": [page_num + 1],
                    "bounding_polygon": polygon,
                    "page_width": page_width,
                    "page_height": page_height
                })
    
                result = search_client.upload_documents(documents=docs)
                for r in result:
                    if not r.succeeded:
                        print(f"[❌] Failed to upload doc ID {r.key}: {r.error_message}")
                    else:
                        print(f"[✅] Uploaded doc ID: {r.key}")
    except Exception as e:
        print(str(e))