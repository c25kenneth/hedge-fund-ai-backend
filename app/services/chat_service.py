from flask import Response, jsonify
from app.db import get_connection
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import MessageRole, BingGroundingTool
from urllib.parse import urlencode
import os
import json

CHATBOT_UUID = "00000000-0000-0000-0000-000000000001"
AGENT_ID = os.environ["AZURE_AGENT_ID"]

agents_client = AgentsClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

bing_tool = BingGroundingTool(connection_id=os.environ["BING_CONNECTION_NAME"])

def handle_chat(request):
    if not request.is_json:
        return jsonify(error="Invalid JSON"), 400

    data = request.get_json()

    def generate_and_store():
        full_response = ""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO messages (sender_uid, receiver_uid, message_text)
                VALUES (?, ?, ?)
            """, (data["uid"], CHATBOT_UUID, data["message"]))
            conn.commit()

            thread = agents_client.threads.create()

            # for msg in data.get("messageContext", []):
            #     agents_client.messages.create(
            #         thread_id=thread.id,
            #         role=msg["role"],
            #         content=msg["content"]
            #     )
            
            agents_client.messages.create(
                thread_id=thread.id,
                role=MessageRole.USER,
                content=data["message"]
            )

            run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=AGENT_ID)

            if run.status == "failed":
                run_details = agents_client.runs.get(thread_id=thread.id, run_id=run.id)
                yield f"[Run failed: {run_details}]"
                return

            # Get final agent response
            response_msg = agents_client.messages.get_last_message_by_role(
                thread_id=thread.id,
                role=MessageRole.AGENT
            )

            # Collect annotations and response text
            annotations = []
            if response_msg and response_msg.text_messages:
                for block in response_msg.text_messages:
                    text_value = block.text.value
                    full_response += text_value
                    for line in text_value.splitlines(keepends=True):
                        yield line

                    if block.text.annotations:
                        for annotation in block.text.annotations:
                            if hasattr(annotation, 'url_citation') and annotation.url_citation:
                                annotations.append(annotation.url_citation.url)
                            elif hasattr(annotation, 'url') and annotation.url:
                                annotations.append(annotation.url)
                            elif hasattr(annotation, 'file_citation') and annotation.file_citation:
                                pass
                            
            bing_search_url = None

            cursor.execute("""
                INSERT INTO messages (sender_uid, receiver_uid, message_text)
                VALUES (?, ?, ?)
            """, (CHATBOT_UUID, data["uid"], full_response))
            conn.commit()

            meta = {
                "type": "metadata",
                "bing_search_url": bing_search_url,
                "sources": annotations
            }
            yield "\n[[META]]" + json.dumps(meta)

        except Exception as e:
            yield f"[Error: {str(e)}]"
        finally:
            conn.close()

    response = Response(generate_and_store(), mimetype='text/plain')
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response