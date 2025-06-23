from flask import Response, jsonify
from openai import AzureOpenAI
from app.db import get_connection
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from werkzeug.utils import secure_filename
from azure.ai.formrecognizer import DocumentAnalysisClient
from urllib.parse import urlencode
from azure.core.credentials import AzureKeyCredential
import os
import json
from app.services.document_service import generate_and_upload_chunks, search_client

CHATBOT_UUID = "00000000-0000-0000-0000-000000000001"
AGENT_ID = os.environ["AZURE_AGENT_ID"]
ALLOWED_EXTENSIONS = {'txt', 'pdf'}
COGN_SERV_ENDPOINT = os.environ["COGN_SERV_ENDPOINT"]
FORM_RECOG_KEY = os.environ["FORM_RECOG_KEY"]
OPENAI_ENDPOINT = os.environ["ENDPOINT"]
OPENAI_SUBSCRIPTION_KEY = os.environ["SUBSCRIPTION_KEY"]
AZURE_SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
AZURE_SEARCH_INDEX=os.environ["AZURE_SEARCH_INDEX"]
AZURE_SEARCH_KEY=os.environ["AZURE_SEARCH_KEY"]

# SETIP API Clients Here
client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint=OPENAI_ENDPOINT,
    api_key=OPENAI_SUBSCRIPTION_KEY,
)

document_analysis_client = DocumentAnalysisClient(
    endpoint=COGN_SERV_ENDPOINT, credential=AzureKeyCredential(FORM_RECOG_KEY)
)

# Valid file?
def allowed_file(filename):
    return '.' in filename and \
       filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# handle user chat no files
def handle_chat(request):
    if not request.is_json:
        return jsonify(error="Invalid JSON"), 400

    data = request.get_json()

    # For if there's no file attached
    def generate_and_store():
        full_response = ""
        conn = get_connection()
        cursor = conn.cursor()

        try:

            # Add previous msesage to sql db
            cursor.execute("""
                INSERT INTO messages (sender_uid, receiver_uid, message_text)
                VALUES (?, ?, ?)
            """, (data["uid"], CHATBOT_UUID, data["message"]))
            conn.commit()

            # Get all messeges in the convo (highkey should turn this into seperate function 💀)
            cursor.execute("""
                SELECT TOP 10 sender_uid, receiver_uid, message_text
                FROM messages
                WHERE sender_uid = ? OR receiver_uid = ?
                ORDER BY sent_at DESC
            """, (data["uid"], data["uid"]))
            chat_history = cursor.fetchall()

            # Get documents uploaded (from search index)
            doc_context = retrieve_doc_content(user_id=data["uid"], prompt=data["message"])
            
            if doc_context:
                references = "\n\n".join(
                    f"[{doc['source']}]\n{doc['text']}" for doc in doc_context
                )
                system_doc_context = (
                    "You have access to the following document excerpts. "
                    "If you use content from them, cite the source by placing the file name in brackets at the end of the relevant sentence — like this: [strategy.pdf].\n\n"
                    f"{references}"
                )
            else:
                system_doc_context = "No relevant document excerpts were found. Answer using general knowledge."

            # For previous messages + documents
            full_chat_context = [
                {
                "role": "system",
                "content": (
                    "You have access to document excerpts provided below. "
                    "If you include any information from these excerpts in your response, "
                    "you must cite the source using the format [filename.pdf] at the END OF THAT sentence. Make sure the sources are BOLDED"
                    "Do not group multiple citations at the end of a paragraph — attach them DIRECTLY TO THE SENTENCE they relate to."
                    "If you do not use any document information, you do not need to cite anything."
                )
                },
                {
                    "role": "system",
                    "content": system_doc_context
                }
            ]

            for row in reversed(chat_history):
                sender_uid, receiver_uid, message_text = row
                role = "user" if sender_uid == data["uid"] else "assistant"
                full_chat_context.append({
                    "role": role,
                    "content": message_text
                })
            
            full_chat_context.append({
                "role": "user",
                "content": data["message"]
            })

            response = client.chat.completions.create(
                stream=True,
                messages=full_chat_context,
                max_tokens=4096,
                temperature=1.0,
                top_p=1.0,
                model="gpt-4o"
            )

            for update in response:
                if update.choices:
                    delta = update.choices[0].delta.content or ""
                    full_response += delta
                    yield delta

            cursor.execute("""
                INSERT INTO messages (sender_uid, receiver_uid, message_text)
                VALUES (?, ?, ?)
            """, (CHATBOT_UUID, data["uid"], full_response))
            conn.commit()

        except Exception as e:
            yield f"[Error: {str(e)}]"
        finally:
            conn.close()

    response = Response(generate_and_store(), mimetype='text/plain')
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response



# hanel user chat when document is attached
def handle_document_chat(request):
    conn = get_connection()
    cursor = conn.cursor()

    file = request.files['file']
    uid = request.form.get("uid")
    message = request.form.get("message", file.filename).strip()
    extracted_text = ""

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        try:
            file.seek(0) 
            poller = document_analysis_client.begin_analyze_document(
                model_id="prebuilt-document",
                document=file,
            )

            result = poller.result()

            for page in result.pages:
                for line in page.lines:
                    extracted_text += line.content + "\n"

            generate_and_upload_chunks(file, uid, filename, result.pages)

        except Exception as e:
            print(f"Error processing document: {str(e)}")
            raise e
    
    def generate_response():
        full_response = ""
        try:
            # Store user message if present
            if message:
                cursor.execute("""
                    INSERT INTO messages (sender_uid, receiver_uid, message_text, file_name)
                    VALUES (?, ?, ?, ?)
                """, (uid, CHATBOT_UUID, f"Uploaded: {file.filename} - {message}", file.filename))
                conn.commit()
            else:
                cursor.execute("""
                    INSERT INTO messages (sender_uid, receiver_uid, message_text, file_name)
                    VALUES (?, ?, ?, ?)
                """, (uid, CHATBOT_UUID, f"Uploaded: {file.filename}", file.filename))
                conn.commit()

            full_chat_context = [{
                "role": "system",
                "content": f"You are a helpful assistant knowledgeable on hedge funds. "
                           f"Answer concisely and clearly. You also may have some knowledge "
                           f"of previously uploaded documents here. Only reference if necessary "
                           f"and relevant: {extracted_text[:1000]}"
            }]

            full_chat_context.append({
                "role": "user",
                "content": message or 'Give a basic rundown'
            })

            response = client.chat.completions.create(
                stream=True,
                messages=full_chat_context,
                max_tokens=4096,
                temperature=1.0,
                top_p=1.0,
                model="gpt-4o"
            )

            for update in response:
                if update.choices:
                    delta = update.choices[0].delta.content or ""
                    full_response += delta
                    yield delta

            # Store assistant response
            cursor.execute("""
                INSERT INTO messages (sender_uid, receiver_uid, message_text)
                VALUES (?, ?, ?)
            """, (CHATBOT_UUID, uid, full_response))
            conn.commit()

        except Exception as e:
            yield f"[Error: {str(e)}]"
        finally:
            conn.close()

    return Response(generate_response(), mimetype='text/plain')


def retrieve_doc_content(user_id, prompt):
    try:
        results = search_client.search(
            search_text=prompt,
            filter=f"user_id eq '{user_id}'",
            select=["text", "source", "blob_url", "page_number", "bounding_polygon"],
            top=5
        )

        docs = []
        for doc in results:
            text = doc.get("text", "")
            source = doc.get("source", "unknown.pdf")
            filename = source.split("/")[-1]

            docs.append({
                "text": text,
                "source": filename,
                "ref": f"[{filename}]",
                "blob_url": doc.get("blob_url"),
                "page_number": doc.get("page_number"),
                "bounding_polygon": doc.get("bounding_polygon")
            })

        return docs if docs else []

    except Exception as e:
        return [{
            "text": f"[Keyword search error: {str(e)}]",
            "source": "error",
            "ref": "[error]",
            "blob_url": None,
            "page_number": None,
            "bounding_polygon": None
        }]