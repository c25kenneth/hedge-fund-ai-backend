from flask import Blueprint, request, jsonify, Response
from app.services.chat_service import handle_chat

chat_bp = Blueprint("chat", __name__)

@chat_bp.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        response = jsonify({"message": "preflight response"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response

    return handle_chat(request)