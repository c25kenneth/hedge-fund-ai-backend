from flask import Response, jsonify, send_file, request
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
import fitz 
import requests
import tempfile
import cv2
import numpy as np

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
                    f"[{doc['source']}]({doc['blob_url']})\n{doc['text']}" for doc in doc_context
                )
                system_doc_context = (
                    "You have access to the following document excerpts. "
                    "you must cite the source using the format **[filename.pdf](blob_url)** at the end of that sentence .\n\n"
                    f"{references}"
                )
            else:
                system_doc_context = "No relevant document excerpts were found. Answer using general knowledge."

            full_chat_context = [
                {
                "role": "system",
                "content": (
                    "You have access to document excerpts provided below. "
                    "If you include any information from these excerpts in your response, "
                    "you must cite the source using the format **[filename.pdf](blob_url)** at the end of that sentence. "
                    "Do not group multiple citations at the end of a paragraph — attach them directly to the sentence they relate to. "
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

            citation_data = [
                {
                    "source": doc["source"],
                    "blob_url": doc["blob_url"],
                    "page_number": doc["page_number"],
                    "bounding_polygon": doc["bounding_polygon"],
                    "page_width": doc["page_width"],
                    "page_height": doc["page_height"],
                } for doc in doc_context
            ] if doc_context else []

            cursor.execute("""
                INSERT INTO messages (sender_uid, receiver_uid, message_text, citations)
                VALUES (?, ?, ?, ?)
            """, (CHATBOT_UUID, data["uid"], full_response, json.dumps(citation_data)))
            conn.commit()

            yield "\n[[CITATION_META]]" + json.dumps(citation_data) + "[[/CITATION_META]]"


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

            cursor.execute("""
                INSERT INTO messages (sender_uid, receiver_uid, message_text, citations)
                VALUES (?, ?, ?, ?)
            """, (CHATBOT_UUID, uid, full_response, json.dumps([])))
            conn.commit()

        except Exception as e:
            yield f"[Error: {str(e)}]"
        finally:
            conn.close()

    return Response(generate_response(), mimetype='text/plain')

def preview_pdf_page():
    url = request.args.get("url")
    page_number = int(request.args.get("page", 1)) - 1
    polygons_str = request.args.get("polygons") 
    
    if not url or not polygons_str:
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        import json
        polygons_data = json.loads(polygons_str)
        
        if not polygons_data or len(polygons_data) == 0:
            return jsonify({"error": "No polygons provided"}), 400

        pdf_response = requests.get(url)
        if pdf_response.status_code != 200:
            return jsonify({"error": "Failed to download PDF"}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(pdf_response.content)
            pdf_path = tmp_pdf.name

        doc = fitz.open(pdf_path)
        if page_number >= len(doc):
            return jsonify({"error": "Page number out of range"}), 400

        page = doc.load_page(page_number)
        dpi = 200
        zoom = dpi / 72  
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        image_path = pdf_path.replace(".pdf", ".png")
        pix.save(image_path)
        doc.close()

        image = cv2.imread(image_path)
        
        colors = [
            (255, 0, 0),
            (0, 255, 0),    
            (0, 0, 255),    
            (255, 255, 0), 
            (255, 0, 255), 
            (0, 255, 255),  
            (128, 0, 128),  
            (255, 165, 0),  
        ]
        
        for i, polygon_in_inches in enumerate(polygons_data):
            if len(polygon_in_inches) % 2 != 0:
                continue 
                
            polygon_pts = [[int(x * dpi), int(y * dpi)] for x, y in zip(polygon_in_inches[::2], polygon_in_inches[1::2])]
            polygon_np = np.array([polygon_pts], dtype=np.int32)
            
            color = colors[i % len(colors)]
            
            thickness = 3 if i == 0 else 2
            cv2.polylines(image, polygon_np, isClosed=True, color=color, thickness=thickness)
            
            if len(polygon_pts) > 0:
                label_pos = (polygon_pts[0][0], polygon_pts[0][1] - 5)
                cv2.putText(image, str(i + 1), label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        output_path = image_path.replace(".png", "_boxed.png")
        cv2.imwrite(output_path, image)

        return send_file(output_path, mimetype="image/png", as_attachment=False)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        for path in [pdf_path, image_path, output_path]:
            if 'path' in locals() and path and os.path.exists(path):
                os.remove(path)


def retrieve_doc_content(user_id, prompt, top_k=3):
    """Improved document retrieval with better filtering"""
    try:
        results = search_client.search(
            search_text=prompt,
            filter=f"user_id eq '{user_id}'",
            select=["text", "source", "blob_url", "page_number", "bounding_polygon", "page_width", "page_height"],
            top=top_k,
        )

        docs = []
        for doc in results:

            # if hasattr(doc, '@search.score') and doc['@search.score'] < 0.85:
                # continue
            text = doc.get("text", "")
            source = doc.get("source", "unknown.pdf")
            filename = source.split("/")[-1]

            docs.append({
                "text": text,
                "source": filename,
                "ref": f"[{filename}]",
                "blob_url": doc.get("blob_url"),
                "page_number": doc.get("page_number"),
                "bounding_polygon": doc.get("bounding_polygon"),
                "page_width": doc.get("page_width"),
                "page_height": doc.get("page_height")
            })
        
        print(f"Retrieved {len(docs)} relevant documents")
        return docs[:top_k]  # Ensure we don't exceed limit

    except Exception as e:
        print(f"Document retrieval error: {str(e)}")
        return []