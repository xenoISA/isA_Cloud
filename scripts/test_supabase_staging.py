#!/usr/bin/env python3
import requests
import json
import time

# Supabase Cloud staging credentials
SUPABASE_URL = "https://ugloxikfljpuvakwiadf.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVnbG94aWtmbGpwdXZha3dpYWRmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTk4MDkzNzcsImV4cCI6MjA3NTM4NTM3N30.-lhB-ggVYD5Foey9rjNv40MkcGhmT9cVcaqvy2y4zro"

# Infrastructure Gateway URL
GATEWAY_URL = "http://localhost:8090"

def test_direct_supabase():
    """Test direct connection to Supabase Cloud"""
    print("\n=== Testing Direct Supabase Cloud Connection ===")
    
    # Test REST API health
    headers = {
        'apikey': SUPABASE_ANON_KEY,
        'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
        'Content-Type': 'application/json'
    }
    
    try:
        # Try to query a simple endpoint
        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/",
            headers=headers
        )
        print(f"REST API Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"Direct connection failed: {e}")
    
    return response.status_code == 200

def test_gateway_supabase():
    """Test Supabase through Infrastructure Gateway"""
    print("\n=== Testing Gateway Supabase Connection ===")
    
    try:
        # Test gateway health
        response = requests.get(f"{GATEWAY_URL}/health")
        print(f"Gateway Health Status: {response.status_code}")
        
        # Test Supabase through gateway
        payload = {
            "operation": "database",
            "params": {
                "action": "query",
                "query": "SELECT 1 as test"
            }
        }
        
        response = requests.post(
            f"{GATEWAY_URL}/api/v1/infra/supabase",
            json=payload
        )
        print(f"Gateway Supabase Query Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"Error: {response.text}")
            
        return response.status_code == 200
    except Exception as e:
        print(f"Gateway connection failed: {e}")
        return False

def create_test_table():
    """Create a test table in Supabase staging"""
    print("\n=== Creating Test Table ===")
    
    headers = {
        'apikey': SUPABASE_ANON_KEY,
        'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    
    # First, check if table exists
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/test_memories",
        headers=headers
    )
    
    if response.status_code == 404:
        print("Table doesn't exist, would need service role key to create it")
        return False
    elif response.status_code == 200:
        print("Table exists, can proceed with tests")
        return True
    else:
        print(f"Unexpected status: {response.status_code}")
        print(f"Response: {response.text}")
        return False

def run_crud_tests():
    """Run basic CRUD operations"""
    print("\n=== Running CRUD Tests ===")
    
    headers = {
        'apikey': SUPABASE_ANON_KEY,
        'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'return=representation'
    }
    
    test_data = {
        "user_id": "test-user-staging",
        "content": f"Test memory at {time.time()}",
        "metadata": {"source": "staging_test"}
    }
    
    # Test INSERT
    print("\n1. Testing INSERT...")
    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/test_memories",
        headers=headers,
        json=test_data
    )
    
    if response.status_code in [200, 201]:
        print("INSERT successful")
        inserted = response.json()
        if isinstance(inserted, list) and len(inserted) > 0:
            memory_id = inserted[0].get('id')
            print(f"Created memory ID: {memory_id}")
            
            # Test SELECT
            print("\n2. Testing SELECT...")
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/test_memories?id=eq.{memory_id}",
                headers=headers
            )
            if response.status_code == 200:
                print(f"SELECT successful: {response.json()}")
            
            # Test UPDATE
            print("\n3. Testing UPDATE...")
            update_data = {"content": "Updated content"}
            response = requests.patch(
                f"{SUPABASE_URL}/rest/v1/test_memories?id=eq.{memory_id}",
                headers=headers,
                json=update_data
            )
            if response.status_code == 200:
                print("UPDATE successful")
            
            # Test DELETE
            print("\n4. Testing DELETE...")
            response = requests.delete(
                f"{SUPABASE_URL}/rest/v1/test_memories?id=eq.{memory_id}",
                headers=headers
            )
            if response.status_code in [200, 204]:
                print("DELETE successful")
    else:
        print(f"INSERT failed with status {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    # Test direct connection first
    direct_ok = test_direct_supabase()
    
    # Test gateway connection
    gateway_ok = test_gateway_supabase()
    
    # Check table and run CRUD if possible
    if direct_ok:
        if create_test_table():
            run_crud_tests()
    
    print("\n=== Test Summary ===")
    print(f"Direct Supabase: {'✓ Connected' if direct_ok else '✗ Failed'}")
    print(f"Gateway Access: {'✓ Connected' if gateway_ok else '✗ Failed'}")