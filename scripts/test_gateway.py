#!/usr/bin/env python3
"""
Simple test script for Infrastructure Gateway
"""

import requests
import json
import time

def test_gateway_health():
    """Test gateway health endpoint"""
    try:
        response = requests.get("http://localhost:8090/health", timeout=5)
        if response.status_code == 200:
            print("✅ Gateway health check passed")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"❌ Gateway health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Gateway connection failed: {e}")
        return False

def test_supabase_operation():
    """Test a simple Supabase operation via gateway"""
    try:
        # Test data
        test_data = {
            "operation": "database",
            "params": {
                "table": "memories",
                "method": "GET",
                "query": {"limit": 1}
            }
        }
        
        print("🧪 Testing Supabase operation via gateway...")
        start_time = time.time()
        
        response = requests.post(
            "http://localhost:8090/api/v1/infra/supabase",
            json=test_data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        end_time = time.time()
        duration = (end_time - start_time) * 1000  # Convert to ms
        
        print(f"⏱️  Request took: {duration:.2f}ms")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Supabase operation successful")
            print(f"   Status: {result.get('success')}")
            print(f"   Service: {result.get('service')}")
            print(f"   Operation: {result.get('operation')}")
            if result.get('error'):
                print(f"   Error: {result.get('error')}")
            return True
        else:
            print(f"❌ Supabase operation failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Supabase test failed: {e}")
        return False

def test_batch_operation():
    """Test batch operations"""
    try:
        batch_data = {
            "parallel": True,
            "requests": [
                {
                    "service": "supabase",
                    "operation": "database",
                    "params": {
                        "table": "memories",
                        "method": "GET",
                        "query": {"limit": 1}
                    }
                },
                {
                    "service": "supabase", 
                    "operation": "database",
                    "params": {
                        "table": "users",
                        "method": "GET", 
                        "query": {"limit": 1}
                    }
                }
            ]
        }
        
        print("🧪 Testing batch operation...")
        start_time = time.time()
        
        response = requests.post(
            "http://localhost:8090/api/v1/infra/batch",
            json=batch_data,
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        
        end_time = time.time()
        duration = (end_time - start_time) * 1000
        
        print(f"⏱️  Batch request took: {duration:.2f}ms")
        
        if response.status_code in [200, 207]:  # 207 = Multi-Status
            result = response.json()
            print("✅ Batch operation completed")
            print(f"   Overall success: {result.get('success')}")
            print(f"   Total time: {result.get('total_time')}")
            print(f"   Results count: {len(result.get('results', []))}")
            
            for i, res in enumerate(result.get('results', [])):
                print(f"   Request {i+1}: {'✅' if res.get('success') else '❌'} ({res.get('service')}/{res.get('operation')})")
                
            return True
        else:
            print(f"❌ Batch operation failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Batch test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Infrastructure Gateway Test Suite")
    print("=" * 40)
    
    # Test 1: Gateway Health
    if not test_gateway_health():
        print("\n❌ Gateway is not running. Please start it first:")
        print("   cd /Users/xenodennis/Documents/Fun/isA_Cloud")
        print("   ./scripts/run_infra_gateway.sh")
        return
    
    print()
    
    # Test 2: Supabase Operation
    test_supabase_operation()
    
    print()
    
    # Test 3: Batch Operation
    test_batch_operation()
    
    print("\n🎉 Test suite completed!")

if __name__ == "__main__":
    main()