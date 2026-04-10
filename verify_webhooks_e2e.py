import os
import requests
import json
import time
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from dotenv import load_dotenv

load_dotenv()

# --- Configuration ---
API_BASE_URL = "http://localhost:8001"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "super-secret-webhook-key")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

PAYLOADS = {
    "sops": {
        "entity_type": "sops",
        "sop_number": "TEST-SOP-001",
        "title": "Webhook Test SOP",
        "department": "Quality Assurance",
        "current_version": {
            "external_status": "active",
            "content_json": {
                "type": "doc",
                "content": [
                    {"type": "heading", "attrs": {"level": 1}, "content": [{"type": "text", "text": "Test Procedure"}]},
                    {"type": "paragraph", "content": [{"type": "text", "text": "This is a test of the automated webhook sync."}]}
                ]
            },
            "metadata_json": {"sopMetadata": {"riskLevel": "Low"}}
        }
    },
    "deviations": {
        "entity_type": "deviations",
        "deviation_number": "DEV-TEST-99",
        "title": "Test Deviation",
        "description_text": "The webhook received this correctly.",
        "root_cause_text": "Automated testing.",
        "impact_level": "Minor",
        "external_status": "open"
    },
    "capas": {
        "entity_type": "capas",
        "capa_number": "CAPA-TEST-1",
        "title": "Test CAPA",
        "action_text": "Verify the logic works.",
        "external_status": "in_progress"
    },
    "decisions": {
        "entity_type": "decisions",
        "decision_number": "DEC-TEST-12",
        "title": "Test Decision",
        "decision_statement": "The sync is working.",
        "rationale_text": "E2E testing."
    },
    "audits": {
        "entity_type": "audits",
        "finding_number": "AUD-TEST-55",
        "finding_text": "Minor finding regarding webhooks.",
        "acceptance_status": "accepted"
    }
}

COL_MAP = {
    "sops": "docs_sops",
    "deviations": "docs_deviations",
    "capas": "docs_capas",
    "decisions": "docs_decisions",
    "audits": "docs_audits"
}

def verify_points(collection, source_id, expected_exists=True):
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
    exists = len(points) > 0
    if expected_exists:
        if exists:
            print(f"  [OK] Points found for {source_id} in {collection}")
            print(f"       Sample content: {points[0].payload.get('page_content')[:50]}...")
            return True
        else:
            print(f"  [FAIL] No points found for {source_id} in {collection}")
            return False
    else:
        if not exists:
            print(f"  [OK] Points successfully deleted for {source_id} in {collection}")
            return True
        else:
            print(f"  [FAIL] Points still exist for {source_id} in {collection}")
            return False

def test_webhook(entity_type, action="update"):
    print(f"\n--- Testing {entity_type.upper()} ({action}) ---")
    payload = PAYLOADS[entity_type].copy()
    payload["action"] = action
    
    headers = {
        "x-webhook-secret": WEBHOOK_SECRET,
        "Content-Type": "application/json"
    }
    
    # Test Auth Failure
    bad_headers = headers.copy()
    bad_headers["x-webhook-secret"] = "wrong-one"
    resp = requests.post(f"{API_BASE_URL}/webhooks/qdrant/sync", json=payload, headers=bad_headers)
    if resp.status_code == 403:
        print("  [OK] Auth failure correctly rejected (403)")
    else:
        print(f"  [FAIL] Auth failure should be 403, got {resp.status_code}")

    # Test Success
    resp = requests.post(f"{API_BASE_URL}/webhooks/qdrant/sync", json=payload, headers=headers)
    if resp.status_code == 202:
        print(f"  [OK] Webhook accepted (202)")
        source_id = payload.get("sop_number") or payload.get("deviation_number") or payload.get("capa_number") or payload.get("decision_number") or payload.get("finding_number")
        return verify_points(COL_MAP[entity_type], source_id, expected_exists=(action != "delete"))
    else:
        print(f"  [FAIL] Webhook rejected: {resp.status_code} - {resp.text}")
        return False

if __name__ == "__main__":
    results = []
    # Test all creates/updates
    for et in PAYLOADS.keys():
        results.append(test_webhook(et, "update"))
    
    # Test one delete
    results.append(test_webhook("sops", "delete"))
    
    print("\n" + "="*40)
    print(f"FINAL RESULT: {results.count(True)}/{len(results)} PASSED")
    print("="*40)
