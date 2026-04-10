import requests
import json
import argparse
import sys

# Configuration - update these if needed
# Using 127.0.0.1 to avoid common 'localhost' resolution issues on Windows
WEBHOOK_URL = "http://127.0.0.1:8000/webhooks/qdrant/sync"
WEBHOOK_SECRET = "my-custom-super-secret-key"

def trigger_sync(action, entity_type, doc_id, data, title=None):
    payload = {
        "action": action,
        "entity_type": entity_type,
        "document_id": doc_id,
        "data": data,
        "title": title
    }
    
    headers = {
        "x-webhook-secret": WEBHOOK_SECRET,
        "Content-Type": "application/json"
    }
    
    print(f"--- Sending {action.upper()} for {doc_id} ({entity_type}) ---")
    try:
        response = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=10)
            
        if response.status_code == 202:
            print("✅ SUCCESS: Request accepted.")
            print(f"Response: {response.json()}")
            print("\nCheck your backend terminal for '[WEBHOOK] SUCCESS' logs.")
        else:
            print(f"❌ FAILED: Status {response.status_code}")
            print(f"Detail: {response.text}")
            
    except Exception as e:
        print(f"❌ ERROR: Could not connect to {WEBHOOK_URL}")
        print(f"Details: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the Qdrant Webhook Sync")
    parser.add_argument("--action", choices=["create", "update", "delete"], default="create")
    parser.add_argument("--type", choices=["sops", "deviations", "capas", "audits", "decisions"], required=True)
    parser.add_argument("--id", required=True, help="Document ID (e.g. DEV-101)")
    parser.add_argument("--text", help="Document content (required for create/update)")
    parser.add_argument("--title", help="Optional document title")
    
    args = parser.parse_args()
    
    if args.action in ["create", "update"] and not args.text:
        print("Error: --text is required for create/update actions.")
        sys.exit(1)
        
    trigger_sync(args.action, args.type, args.id, args.text, args.title)
