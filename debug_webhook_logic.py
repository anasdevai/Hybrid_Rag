import os
import sys
import logging
from dotenv import load_dotenv

# Add parent dir to path
sys.path.append(os.getcwd())

load_dotenv()

from routers.webhooks import _process_sync

# Configure logging to console
logging.basicConfig(level=logging.INFO)

# Test SOP update
print("\n=== DEBUGGING SOP SYNC ===")
sop_payload = {
    "entity_type": "sops",
    "sop_number": "DEBUG-SOP-001",
    "title": "Debug SOP",
    "department": "IT",
    "current_version": {
        "external_status": "draft",
        "content_json": {
            "type": "doc",
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Debug content."}]}]
        }
    }
}

try:
    # Run the background task logic synchronously for debugging
    _process_sync("sops", "update", sop_payload)
    print("Execution finished without crash.")
except Exception as e:
    print(f"CRASHED: {e}")
    import traceback
    traceback.print_exc()

import time
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

qdrant_url = os.getenv("QDRANT_URL")
qdrant_api_key = os.getenv("QDRANT_API_KEY")
client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)

time.sleep(1)
res = client.scroll(
    collection_name="docs_sops",
    scroll_filter=Filter(
        must=[FieldCondition(key="source_id", match=MatchValue(value="DEBUG-SOP-001"))]
    )
)
print(f"Found points: {len(res[0])}")
if res[0]:
    print(f"Payload matching source_id 'DEBUG-SOP-001': {res[0][0].payload.get('page_content')[:50]}...")
