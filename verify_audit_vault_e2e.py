import asyncio
import os
import httpx
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

load_dotenv()

API_URL = "http://127.0.0.1:8000"

async def verify_e2e():
    # 1. Register and Get a token
    print("--- Step 1: Authentication ---")
    email = f"audit_test_{os.urandom(2).hex()}@example.com"
    password = "AdminPassword123!" # Meets strength requirements
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # Try to register first
            print(f"Registering user: {email}...")
            await client.post(f"{API_URL}/auth/register", json={
                "email": email,
                "username": f"audit_user_{os.urandom(2).hex()}",
                "password": password,
                "confirm_password": password
            })
            
            # Log in
            print("Logging in...")
            resp = await client.post(f"{API_URL}/auth/login", json={
                "email": email,
                "password": password
            })
            resp.raise_for_status()
            token = resp.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            print("[OK] Authenticated successfully.")
        except Exception as e:
            print(f"[FAIL] Auth/Reg failed: {e}")
            if hasattr(e, 'response'):
                print(f"Detail: {e.response.text}")
            return

        # 2. Create a session
        print("\n--- Step 2: Create Session ---")
        resp = await client.post(f"{API_URL}/chat/sessions", 
                               json={"title": "Audit Vault Verification"}, 
                               headers=headers)
        resp.raise_for_status()
        session_id = resp.json()["id"]
        print(f"[OK] Session created: {session_id}")

        # 3. Trigger Smart Query
        print("\n--- Step 3: Trigger Smart Query ---")
        query = "What is the access control policy?"
        resp = await client.post(f"{API_URL}/query/smart", 
                               json={"query": query}, 
                               headers=headers)
        resp.raise_for_status()
        data = resp.json()
        print(f"[OK] Received response. Answer snippet: {data['answer'][:50]}...")
        
        # Verify Snapshots are in the API response
        print(f"  - metadata_snapshot items: {len(data.get('metadata_snapshot', []))}")
        print(f"  - audit_log_snapshot items: {len(data.get('audit_log_snapshot', []))}")
        print(f"  - action_metadata keys: {list(data.get('action_metadata', {}).keys())}")

        # 4. Save to DB (Simulating what the frontend does)
        print("\n--- Step 4: Save to Database ---")
        save_resp = await client.post(f"{API_URL}/chat/sessions/{session_id}/messages", 
                                   json={
                                       "session_id": session_id,
                                       "role": "assistant",
                                       "content": data["answer"],
                                       "citations": data["citations"],
                                       "retrieval_metadata": {"suggestions": data["suggestions"], "stats": data["retrieval_stats"]},
                                       "metadata_snapshot": data["metadata_snapshot"],
                                       "audit_log_snapshot": data["audit_log_snapshot"],
                                       "action_metadata": data["action_metadata"]
                                   }, 
                                   headers=headers)
        save_resp.raise_for_status()
        msg_id = save_resp.json()["id"]
        print(f"[OK] Message saved: {msg_id}")

    # 5. Check Postgres directly
    print("\n--- Step 5: Verify Postgres Columns ---")
    user = os.getenv("POSTGRES_USER", "postgres")
    pw = os.getenv("POSTGRES_PASSWORD", "admin123")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "qdrant")
    url = f"postgresql+asyncpg://{user}:{pw}@{host}:{port}/{db_name}"
    
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        q = text("SELECT id, metadata_snapshot, audit_log_snapshot, action_metadata FROM chat_messages WHERE id = :mid")
        row = await conn.execute(q, {"mid": msg_id})
        result = row.fetchone()
        
        if result:
            print(f"[VERIFIED] Message {result.id} in Postgres has:")
            print(f"  - metadata_snapshot: {'YES' if result.metadata_snapshot else 'NO'}")
            print(f"  - audit_log_snapshot: {'YES' if result.audit_log_snapshot else 'NO'}")
            print(f"  - action_metadata: {'YES' if result.action_metadata else 'NO'}")
            
            if result.metadata_snapshot and result.audit_log_snapshot:
                print("\n🎉 AUDIT VAULT SUCCESSFULLY IMPLEMENTED!")
            else:
                print("\n⚠️ Snapshot data found but appearing empty. Verify ingestion content.")
        else:
            print("[FAIL] Could not find message in database.")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_e2e())
