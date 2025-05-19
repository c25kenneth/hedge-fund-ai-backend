from flask import Response, jsonify
from app.config import Config
from app.db import get_connection
from openai import AzureOpenAI

client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint=Config.ENDPOINT,
    api_key=Config.SUBSCRIPTION_KEY,
)

CHATBOT_UUID = "00000000-0000-0000-0000-000000000001"

def handle_chat(request):
    if not request.is_json:
        return jsonify(error="Invalid JSON"), 400

    data = request.get_json()

    def generate_and_store():
        full_response = ""
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO messages (sender_uid, receiver_uid, message_text)
            VALUES (?, ?, ?)
        """, (data["uid"], CHATBOT_UUID, data["message"]))
        conn.commit()

        response = client.chat.completions.create(
            stream=True,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                *data["messageContext"],
                {"role": "user", "content": data["message"]},
            ],
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
        conn.close()

    response = Response(generate_and_store(), mimetype='text/plain')
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response
