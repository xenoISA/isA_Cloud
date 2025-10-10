#!/usr/bin/env python3
"""
Performance Testing Script: Python Direct vs Go Gateway
Compares performance between direct Supabase access and Infrastructure Gateway
"""

import asyncio
import time
import statistics
import json
import sys
import os
from typing import List, Dict, Any
import aiohttp
import requests
from datetime import datetime

# Add the user path to import the Supabase client
sys.path.append('/Users/xenodennis/Documents/Fun/isA_user')
from core.database.supabase_client import get_supabase_client

class PerformanceTester:
    def __init__(self):
        self.gateway_url = "http://localhost:8090"
        self.supabase_client = get_supabase_client()
        self.results = {
            "direct": [],
            "gateway": []
        }
        
    async def test_direct_supabase(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Test direct Supabase access via Python client"""
        start_time = time.perf_counter()
        
        try:
            if operation == "get_memory":
                result = await self.supabase_client.get_memory(params["key"])
            elif operation == "set_memory":
                result = await self.supabase_client.set_memory(
                    params["key"], 
                    params["value"], 
                    params.get("category", "test"),
                    params.get("importance", 1)
                )
            elif operation == "search_memories":
                result = await self.supabase_client.search_memories(
                    params["query"],
                    params.get("category"),
                    params.get("limit", 10)
                )
            elif operation == "generic_select":
                result = await self.supabase_client.execute_query(
                    params["table"],
                    "select",
                    filters=params.get("filters")
                )
            else:
                raise ValueError(f"Unknown operation: {operation}")
                
            end_time = time.perf_counter()
            
            return {
                "success": True,
                "duration": end_time - start_time,
                "result": result,
                "error": None
            }
            
        except Exception as e:
            end_time = time.perf_counter()
            return {
                "success": False,
                "duration": end_time - start_time,
                "result": None,
                "error": str(e)
            }
    
    async def test_gateway_supabase(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Test Supabase access via Infrastructure Gateway"""
        start_time = time.perf_counter()
        
        try:
            gateway_params = self._convert_to_gateway_params(operation, params)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.gateway_url}/api/v1/infra/supabase",
                    json={
                        "operation": "database",
                        "params": gateway_params
                    },
                    headers={"Content-Type": "application/json"}
                ) as response:
                    result = await response.json()
                    
            end_time = time.perf_counter()
            
            return {
                "success": result.get("success", False),
                "duration": end_time - start_time,
                "result": result.get("data"),
                "error": result.get("error")
            }
            
        except Exception as e:
            end_time = time.perf_counter()
            return {
                "success": False,
                "duration": end_time - start_time,
                "result": None,
                "error": str(e)
            }
    
    def _convert_to_gateway_params(self, operation: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Convert operation parameters to gateway format"""
        if operation == "get_memory":
            return {
                "table": "memories",
                "method": "GET",
                "query": {"eq": {"key": params["key"]}}
            }
        elif operation == "set_memory":
            # Check if memory exists first, then update or insert
            return {
                "table": "memories",
                "method": "POST",
                "data": {
                    "key": params["key"],
                    "value": params["value"],
                    "category": params.get("category", "test"),
                    "importance": params.get("importance", 1),
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
            }
        elif operation == "search_memories":
            return {
                "table": "memories",
                "method": "GET",
                "query": {
                    "or": f'key.ilike.%{params["query"]}%,value.ilike.%{params["query"]}%',
                    "order": "importance.desc",
                    "limit": params.get("limit", 10)
                }
            }
        elif operation == "generic_select":
            return {
                "table": params["table"],
                "method": "GET",
                "query": params.get("filters", {})
            }
        else:
            raise ValueError(f"Unknown operation: {operation}")
    
    async def run_performance_test(self, operation: str, params: Dict[str, Any], iterations: int = 100):
        """Run performance test comparing direct vs gateway access"""
        print(f"\n🧪 Testing operation: {operation}")
        print(f"📊 Iterations: {iterations}")
        print(f"⚙️  Parameters: {json.dumps(params, indent=2)}")
        
        # Test direct access
        print("\n📡 Testing Direct Supabase Access...")
        direct_results = []
        for i in range(iterations):
            result = await self.test_direct_supabase(operation, params)
            direct_results.append(result)
            if (i + 1) % 10 == 0:
                print(f"  ✅ Completed {i + 1}/{iterations} direct tests")
        
        # Test gateway access
        print("\n🌐 Testing Gateway Access...")
        gateway_results = []
        for i in range(iterations):
            result = await self.test_gateway_supabase(operation, params)
            gateway_results.append(result)
            if (i + 1) % 10 == 0:
                print(f"  ✅ Completed {i + 1}/{iterations} gateway tests")
        
        # Store results
        self.results["direct"].extend(direct_results)
        self.results["gateway"].extend(gateway_results)
        
        # Analyze results
        self.analyze_results(operation, direct_results, gateway_results)
    
    def analyze_results(self, operation: str, direct_results: List[Dict], gateway_results: List[Dict]):
        """Analyze and display performance results"""
        print(f"\n📈 Performance Analysis for {operation}")
        print("=" * 60)
        
        # Filter successful requests
        direct_success = [r for r in direct_results if r["success"]]
        gateway_success = [r for r in gateway_results if r["success"]]
        
        # Calculate statistics
        if direct_success:
            direct_times = [r["duration"] * 1000 for r in direct_success]  # Convert to ms
            direct_stats = {
                "count": len(direct_success),
                "avg": statistics.mean(direct_times),
                "median": statistics.median(direct_times),
                "min": min(direct_times),
                "max": max(direct_times),
                "std": statistics.stdev(direct_times) if len(direct_times) > 1 else 0
            }
        else:
            direct_stats = {"count": 0, "avg": 0, "median": 0, "min": 0, "max": 0, "std": 0}
        
        if gateway_success:
            gateway_times = [r["duration"] * 1000 for r in gateway_success]  # Convert to ms
            gateway_stats = {
                "count": len(gateway_success),
                "avg": statistics.mean(gateway_times),
                "median": statistics.median(gateway_times),
                "min": min(gateway_times),
                "max": max(gateway_times),
                "std": statistics.stdev(gateway_times) if len(gateway_times) > 1 else 0
            }
        else:
            gateway_stats = {"count": 0, "avg": 0, "median": 0, "min": 0, "max": 0, "std": 0}
        
        # Display results
        print("\n🐍 Direct Python Access:")
        print(f"  ✅ Success Rate: {len(direct_success)}/{len(direct_results)} ({len(direct_success)/len(direct_results)*100:.1f}%)")
        print(f"  ⏱️  Average: {direct_stats['avg']:.2f}ms")
        print(f"  📊 Median: {direct_stats['median']:.2f}ms")
        print(f"  ⚡ Min: {direct_stats['min']:.2f}ms")
        print(f"  🐌 Max: {direct_stats['max']:.2f}ms")
        print(f"  📏 Std Dev: {direct_stats['std']:.2f}ms")
        
        print("\n🚀 Go Gateway Access:")
        print(f"  ✅ Success Rate: {len(gateway_success)}/{len(gateway_results)} ({len(gateway_success)/len(gateway_results)*100:.1f}%)")
        print(f"  ⏱️  Average: {gateway_stats['avg']:.2f}ms")
        print(f"  📊 Median: {gateway_stats['median']:.2f}ms")
        print(f"  ⚡ Min: {gateway_stats['min']:.2f}ms")
        print(f"  🐌 Max: {gateway_stats['max']:.2f}ms")
        print(f"  📏 Std Dev: {gateway_stats['std']:.2f}ms")
        
        # Performance comparison
        if direct_stats["avg"] > 0 and gateway_stats["avg"] > 0:
            if gateway_stats["avg"] < direct_stats["avg"]:
                improvement = ((direct_stats["avg"] - gateway_stats["avg"]) / direct_stats["avg"]) * 100
                print(f"\n🎉 Gateway is {improvement:.1f}% FASTER than direct access!")
            else:
                degradation = ((gateway_stats["avg"] - direct_stats["avg"]) / direct_stats["avg"]) * 100
                print(f"\n⚠️ Gateway is {degradation:.1f}% SLOWER than direct access")
                
        # Error analysis
        direct_errors = [r for r in direct_results if not r["success"]]
        gateway_errors = [r for r in gateway_results if not r["success"]]
        
        if direct_errors:
            print(f"\n❌ Direct Access Errors ({len(direct_errors)}):")
            for error in direct_errors[:3]:  # Show first 3 errors
                print(f"  - {error['error']}")
                
        if gateway_errors:
            print(f"\n❌ Gateway Access Errors ({len(gateway_errors)}):")
            for error in gateway_errors[:3]:  # Show first 3 errors
                print(f"  - {error['error']}")
    
    def check_gateway_health(self) -> bool:
        """Check if Infrastructure Gateway is running"""
        try:
            response = requests.get(f"{self.gateway_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    async def run_comprehensive_test(self):
        """Run comprehensive performance tests"""
        print("🚀 Infrastructure Gateway Performance Testing")
        print("=" * 50)
        
        # Check gateway health
        if not self.check_gateway_health():
            print("❌ Infrastructure Gateway is not running!")
            print(f"   Please start the gateway at {self.gateway_url}")
            print("   Run: go run cmd/infra-gateway/main.go")
            return
        
        print("✅ Infrastructure Gateway is running")
        
        # Test scenarios
        test_scenarios = [
            {
                "operation": "get_memory",
                "params": {"key": "test_key_performance"},
                "iterations": 50
            },
            {
                "operation": "set_memory",
                "params": {
                    "key": f"perf_test_{int(time.time())}",
                    "value": "Performance test data",
                    "category": "testing",
                    "importance": 1
                },
                "iterations": 30
            },
            {
                "operation": "search_memories",
                "params": {
                    "query": "test",
                    "limit": 10
                },
                "iterations": 20
            }
        ]
        
        # Run tests
        for scenario in test_scenarios:
            await self.run_performance_test(
                scenario["operation"],
                scenario["params"],
                scenario["iterations"]
            )
        
        # Generate summary report
        self.generate_summary_report()
    
    def generate_summary_report(self):
        """Generate a summary performance report"""
        print("\n" + "=" * 60)
        print("📋 PERFORMANCE SUMMARY REPORT")
        print("=" * 60)
        
        if not self.results["direct"] or not self.results["gateway"]:
            print("❌ No test results available for summary")
            return
        
        # Overall statistics
        direct_times = [r["duration"] * 1000 for r in self.results["direct"] if r["success"]]
        gateway_times = [r["duration"] * 1000 for r in self.results["gateway"] if r["success"]]
        
        if direct_times and gateway_times:
            direct_avg = statistics.mean(direct_times)
            gateway_avg = statistics.mean(gateway_times)
            
            print(f"\n📊 Overall Average Response Times:")
            print(f"   🐍 Python Direct:  {direct_avg:.2f}ms")
            print(f"   🚀 Go Gateway:     {gateway_avg:.2f}ms")
            
            if gateway_avg < direct_avg:
                improvement = ((direct_avg - gateway_avg) / direct_avg) * 100
                print(f"   🎉 Gateway Performance: {improvement:.1f}% FASTER")
            else:
                degradation = ((gateway_avg - direct_avg) / direct_avg) * 100
                print(f"   ⚠️  Gateway Performance: {degradation:.1f}% SLOWER")
        
        # Success rates
        direct_success_rate = len([r for r in self.results["direct"] if r["success"]]) / len(self.results["direct"]) * 100
        gateway_success_rate = len([r for r in self.results["gateway"] if r["success"]]) / len(self.results["gateway"]) * 100
        
        print(f"\n✅ Success Rates:")
        print(f"   🐍 Python Direct:  {direct_success_rate:.1f}%")
        print(f"   🚀 Go Gateway:     {gateway_success_rate:.1f}%")
        
        # Recommendations
        print(f"\n💡 Recommendations:")
        if gateway_avg < direct_avg:
            print("   ✅ Consider using Infrastructure Gateway for production")
            print("   🚀 Gateway provides better performance and centralized management")
        else:
            print("   ⚠️  Gateway adds latency - consider optimizations:")
            print("   📈 Connection pooling, caching, or batch operations")
        
        print(f"\n📝 Test completed at: {datetime.now().isoformat()}")

async def main():
    """Main entry point"""
    tester = PerformanceTester()
    await tester.run_comprehensive_test()

if __name__ == "__main__":
    asyncio.run(main())