import requests
import json
import time

base_url = "http://localhost:5020/api"

def test_interaction():
    # 0. Get available indices to be sure
    print("--- Fetching Indices ---")
    idx_resp = requests.get(f"{base_url}/get_indices", params={"name": "os-std"})
    print(f"Indices: {idx_resp.text}")
    indices = idx_resp.json()
    if not indices:
        print("Error: No indices found for os-std")
        return
    sample_idx = indices[-1] # Try the last one

    # 1. Start Sample
    print(f"\n--- Testing Start Sample (index={sample_idx}) ---")
    start_payload = {
        "name": "os-std",
        "index": sample_idx
    }
    resp = requests.post(f"{base_url}/start_sample", json=start_payload)
    print(f"Status: {resp.status_code}")
    print(f"Body: {resp.text}")
    print(f"Headers: {dict(resp.headers)}")
    
    sid = resp.headers.get("Session_id") or resp.headers.get("X-Session-Id") or resp.headers.get("session_id")
    print(f"Session ID: {sid}")
    
    # Wait a bit for worker to initialize
    print("Waiting 3s for worker initialization...")
    time.sleep(3)
    
    # Check sessions
    resp = requests.get(f"{base_url}/get_sessions")
    print(f"Active Sessions: {resp.text}")
    
    if not sid:
        print("Error: No Session ID in headers")
        return

    print(f"Got Session ID: {sid}")

    # 2. Test Interact
    print("\n--- Testing Interact ---")
    
    # Combinations of body, headers, and URL params
    # Test 0: Body Only (Standard)
    # Test 1: Body + Header (What we've been trying)
    # Test 2: URL Param + Body
    # Test 3: URL Param + Body + Header
    
    tests = [
        # Variant 0: Nested (what host code does)
        {"url": f"{base_url}/interact", "body": {"session_id": int(sid), "agent_response": {"messages": [{"role": "assistant", "content": "ls"}], "status": "normal"}}, "headers": {"Session_id": str(sid)}},
        # Variant 1: Flat (what worker typings suggest)
        {"url": f"{base_url}/interact", "body": {"session_id": int(sid), "messages": [{"role": "assistant", "content": "ls"}], "status": "normal"}, "headers": {"Session_id": str(sid)}},
        # Variant 2: Flat no status
        {"url": f"{base_url}/interact", "body": {"session_id": int(sid), "messages": [{"role": "assistant", "content": "ls"}]}, "headers": {"Session_id": str(sid)}},
    ]
    
    for i, t in enumerate(tests):
        print(f"\n[Test {i}] URL: {t['url']}, Body keys: {list(t['body'].keys())}, Headers: {t['headers']}")
        resp = requests.post(t['url'], json=t['body'], headers=t['headers'])
        print(f"Status: {resp.status_code}")
        print(f"Body: {resp.text}")
        if resp.status_code == 200:
            print("SUCCESS!")
            break

if __name__ == "__main__":
    test_interaction()
