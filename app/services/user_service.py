from flask import request, jsonify
from app.db import get_connection
import json 

def create_user(request):
    try:
        data = request.get_json()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO [user] (uid) VALUES (?)", data["uid"])
        conn.commit()
        conn.close()
        return "User successfully added"
    except Exception:
        return "User already exists"

def get_user_chat(request):
    try:
        data = request.get_json()
        uid = data['uid']

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM messages
            WHERE sender_uid = ? OR receiver_uid = ?
            ORDER BY sent_at ASC
        """, (uid, uid))

        rows = cursor.fetchall()
        conn.close()

        messages = [
            {
                "id": row.id,
                "sender_uid": row.sender_uid,
                "receiver_uid": row.receiver_uid,
                "message_text": row.message_text,
                "file_name": row.file_name if hasattr(row, 'file_name') else None,
                "timestamp": row.sent_at.isoformat() if hasattr(row, 'sent_at') else None, 
                "citations": json.loads(row.citations) if row.citations else [],
            }
            for row in rows
        ]
        return jsonify(messages)
    except Exception as e:
        print("DB Error:", e)
        return jsonify(error="Couldn't get rows: " + str(e)), 500
