"""Test webhook GET endpoint locally and print full error."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=True)
try:
    r = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": os.getenv("VERIFY_TOKEN", ""),
            "hub.challenge": "TEST123",
        },
    )
    print("Status:", r.status_code)
    print("Body:", r.text)
except Exception as e:
    import traceback
    traceback.print_exc()
