# 🧠 Hedge Fund AI Chat — Python Backend

Python + Flask backend for the Hedge Fund AI Chat app. Uses Supabase for OAuth2 authentication. Azure SQL databases for backend.

---

## Features

- ✅ Domain-specific knowledge of hedge funds via Azure AI Search (with Azure Blob Storage)
- 🗂 Chat history fetch and storage (Azure SQL Databases)
- 🤖 AI assistant using Azure OpenAI models (also used blob storage for domain specific knowledge as well as Azure SQL databases for conversation context)
- 🧪 Used Flask REST API local development

---

## To Get Started

### 1. Clone the Repo

```bash
git clone https://github.com/c25kenneth/hedge-fund-ai-backend.git
cd hedge-fund-ai-backend
```

### 2. Set up virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
```bash
cp .env.example .env
```

Then update with relevant variables
```bash
SUBSCRIPTION_KEY=your_azure_subscription_key
ENDPOINT=your_openai_service_endpoint
DB_USERNAME=your_azure_sql_db_username
DB_PASSWORD=your_azure_sql_db_password
```

### 5. Run the backend
```bash
python run.py
```
