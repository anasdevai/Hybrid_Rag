import os
import sys
import logging
import asyncio
from dotenv import load_dotenv

# Add parent dir to path
sys.path.append(os.getcwd())

load_dotenv()

from routers.webhooks import _process_sync
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

# Configure logging to console
logging.basicConfig(level=logging.INFO)

async def debug_put_logic():
    print("\n=== DEBUGGING PUT LOGIC (Idempotent Update) ===")
    
    source_id = "DIRECT-PUT-TEST-001"
    
    # 1. Simulate "Create" (Update action)
    payload_1 = {
        "sop_number": source_id,
        "title": "Direct PUT Test",
        "current_version": {
            "content_json": {
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Original Version Content."}]}]
            }
        }
    }
    
    print(f"Executing sync job 1 for {source_id}...")
    _process_sync("sops", "update", payload_1)
    
    # 2. Simulate "Replace" (Update action)
    payload_2 = payload_1.copy()
    payload_2["current_version"]["content_json"]["content"][0]["content"][0]["text"] = "Replaced Version Content via PUT logic."
    
    print(f"Executing sync job 2 (replacement) for {source_id}...")
    _process_sync("sops", "update", payload_2)
    
    # 3. Verify in Qdrant
    print("Verifying final state in Qdrant...")
    client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
    
    res = client.scroll(
        collection_name="docs_sops",
        scroll_filter=Filter(
            must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
        ),
        with_payload=True
    )
    
    points = res[0]
    print(f"Found points: {len(points)}")
    if points:
        content = points[0].payload.get("page_content", "")
        print(f"Final Content: {content}")
        if "Replaced Version Content" in content:
            print("SUCCESS: PUT logic correctly replaced the existing vectors.")
            return True
    
    print("FAIL: PUT logic did not correctly replace vectors.")
    return False

if __name__ == "__main__":
    success = asyncio.run(debug_put_logic())
    sys.exit(0 if success else 1)
