import asyncio
import httpx

async def test_rag():
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            print("Registering user...")
            register_res = await client.post("http://127.0.0.1:8000/auth/register", json={
                "email": "testrag@example.com",
                "username": "testrag",
                "password": "Password123!",
                "confirm_password": "Password123!"
            })
            
            print("Logging in...")
            login_res = await client.post("http://127.0.0.1:8000/auth/login", json={
                "email": "testrag@example.com",
                "password": "Password123!"
            })
            if login_res.status_code != 200:
                print("Login failed:", login_res.text)
                return
            
            token = login_res.json()["access_token"]
            print("Obtained Token:", token[:20], "...")
            
            print("\nQuerying RAG...")
            query_res = await client.post("http://127.0.0.1:8000/query", json={
                "query": "What are the compliance steps?"
            }, headers={"Authorization": f"Bearer {token}"})
            
            print("\nResponse Status:", query_res.status_code)
            try:
                import json
                print("\nResponse JSON:")
                print(json.dumps(query_res.json(), indent=2))
            except Exception as e:
                print("Could not parse JSON:", e)
                print(query_res.text)
            
    except Exception as e:
        print("Error connecting to server:", e)

if __name__ == "__main__":
    asyncio.run(test_rag())
