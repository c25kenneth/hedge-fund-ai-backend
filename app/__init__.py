from flask import Flask
from flask_cors import CORS
from app.routes.chat_routes import chat_bp
from app.routes.user_routes import user_bp

UPLOAD_FOLDER = "uploads"

def create_app():
    app = Flask(__name__)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    CORS(app)
    # CORS(app, resources={r"/*": {"origins": "https://gentle-dune-04f5fbc1e.6.azurestaticapps.net"}}, supports_credentials=True)

    app.register_blueprint(chat_bp)
    app.register_blueprint(user_bp)

    return app