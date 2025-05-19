from flask import Blueprint, request, jsonify
from app.services.user_service import create_user, get_user_chat

user_bp = Blueprint("user", __name__)

@user_bp.route("/createUser", methods=["POST", "OPTIONS"])
def create_user_route():
    if request.method == "OPTIONS":
        response = jsonify({"message": "preflight response"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response

    return create_user(request)

@user_bp.route("/getUserChat", methods=["POST", "OPTIONS"])
def get_user_chat_route():
    if request.method == "OPTIONS":
        response = jsonify({"message": "preflight response"})
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type")
        response.headers.add("Access-Control-Allow-Methods", "POST")
        return response

    return get_user_chat(request)
