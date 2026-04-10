import requests
import time
import sys
import os

# Configuration
API_BASE_URL = "http://localhost:8000"

def test_auth_patch():
    print("--- Testing PATCH /auth/me ---")
    
    # 1. Register a fresh test user
    timestamp = int(time.time())
    username = f"patch_user_{timestamp}"
    email = f"patch_{timestamp}@example.com"
    password = "TestPassword123"
    
    print(f"Registering user: {username}")
    reg_resp = requests.post(f"{API_BASE_URL}/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
        "confirm_password": password
    })
    
    if reg_resp.status_code != 201:
        print(f"Registration failed: {reg_resp.text}")
        return False
        
    # 2. Login to get token
    print("Logging in...")
    login_resp = requests.post(f"{API_BASE_URL}/auth/login", data={
        "username": username,
        "password": password
    })
    
    if login_resp.status_code != 200:
        print(f"Login failed: {login_resp.text}")
        return False
        
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Verify initial state
    print("Verifying initial state...")
    me_resp = requests.get(f"{API_BASE_URL}/auth/me", headers=headers)
    if me_resp.json()["username"] != username:
        print(f"Initial username mismatch!")
        return False
        
    # 4. Perform PATCH update (change username)
    new_username = f"updated_{username}"
    print(f"UPDATING username to: {new_username}")
    patch_resp = requests.patch(f"{API_BASE_URL}/auth/me", headers=headers, json={
        "username": new_username
    })
    
    if patch_resp.status_code != 200:
        print(f"PATCH failed: {patch_resp.status_code} - {patch_resp.text}")
        return False
        
    if patch_resp.json()["username"] != new_username:
        print(f"PATCH response did not return new username!")
        return False
        
    # 5. Verify persistence via GET
    print("Verifying persistence via GET /auth/me...")
    verify_resp = requests.get(f"{API_BASE_URL}/auth/me", headers=headers)
    if verify_resp.json()["username"] == new_username:
        print("SUCCESS: Username was properly updated and persisted.")
        return True
    else:
        print("FAIL: Username was not persisted in database.")
        return False

if __name__ == "__main__":
    success = test_auth_patch()
    sys.exit(0 if success else 1)
