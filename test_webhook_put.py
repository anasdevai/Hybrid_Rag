import os
import requests
import time
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
API_BASE_URL = "http://localhost:8000"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "super-secret-webhook-key")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def verify_points(collection, source_id, expected_content):
    time.sleep(3) # Wait for background task
    res = client.scroll(
        collection_name=collection,
        scroll_filter=Filter(
            must=[FieldCondition(key="source_id", match=MatchValue(value=str(source_id)))]
        ),
        limit=1,
        with_payload=True
    )
    points = res[0]
    if not points:
        print(f"  [FAIL] No points found for {source_id} in {collection}")
        return False
    
    actual_content = points[0].payload.get("page_content", "")
    if expected_content in actual_content:
        print(f"  [OK] Points found and content matches: '{expected_content}'")
        return True
    else:
        print(f"  [FAIL] Content mismatch. Expected substring '{expected_content}', got '{actual_content[:50]}...'")
        return False

def test_webhook_put():
    print("\n--- Testing Webhook PUT (Idempotent Update) ---")
    
    source_id = "PUT-TEST-SOP-555"
    payload = {
        "sop_number": source_id,
        "title": "Initial PUT SOP",
        "current_version": {
            "content_json": {
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "First version content."}]}]
            }
        }
    }
    
    headers = {
        "x-webhook-secret": WEBHOOK_SECRET,
        "Content-Type": "application/json"
    }

    # 1. First PUT (Create)
    print(f"Sending first PUT for {source_id}...")
    resp = requests.put(f"{API_BASE_URL}/webhooks/qdrant/sync", json=payload, headers=headers)
    if resp.status_code != 202:
        print(f"  [FAIL] PUT rejected: {resp.status_code} - {resp.text}")
        return False
    
    if not verify_points("docs_sops", source_id, "First version content."):
        return False

    # 2. Second PUT (Update/Replace)
    print(f"Sending second PUT (update) for {source_id}...")
    payload["current_version"]["content_json"]["content"][0]["content"][0]["text"] = "Updated version content via PUT."
    resp = requests.put(f"{API_BASE_URL}/webhooks/qdrant/sync", json=payload, headers=headers)
    if resp.status_code != 202:
        print(f"  [FAIL] Second PUT rejected: {resp.status_code}")
        return False

    if not verify_points("docs_sops", source_id, "Updated version content via PUT."):
        return False

    print("\nSUCCESS: Native HTTP PUT method verified for idempotent replacement.")
    return True

if __name__ == "__main__":
    success = test_webhook_put()
    import sys
    sys.exit(0 if success else 1)
