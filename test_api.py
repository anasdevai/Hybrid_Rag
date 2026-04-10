from fastapi.testclient import TestClient
from main import app
import sys

# Initialize client. The startup events run automatically when using TestClient within a "with" block.
with TestClient(app) as client:
    print("Testing GET /health endpoint...")
    response = client.get("/health")
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}\n")
    if response.status_code != 200:
        print("Healthcheck failed!")
        sys.exit(1)

    print("Testing POST /query endpoint...")
    payload = {
        "query": "Based on the text that mentions 'fuga et accusamus dolorum perferendis illo voluptas', what happens next according to the document?"
    }
    response = client.post("/query", json=payload)
    print(f"Status Code: {response.status_code}")
    resp_json = response.json()
    print(f"Answer: {resp_json.get('answer')}")
    print(f"Citations Used: {len(resp_json.get('citations', []))}")
    if response.status_code != 200:
        print("Query endpoint failed!")
        sys.exit(1)

print("\nAll routes tested successfully!")
