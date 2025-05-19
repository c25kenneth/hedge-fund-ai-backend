import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SERVER = 'albert-ai-proj-server.database.windows.net'
    DATABASE = 'albert-ai-proj-sql-db'
    USERNAME = os.getenv("DB_USERNAME")
    PASSWORD = os.getenv("DB_PASSWORD")
    ENDPOINT = os.getenv("ENDPOINT")
    SUBSCRIPTION_KEY = os.getenv("SUBSCRIPTION_KEY")