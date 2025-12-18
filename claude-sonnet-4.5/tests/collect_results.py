"""
Post-change results collector.
Runs the greenfield system and collects detailed metrics.
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from graph import Graph
from service import RoutingService, RouteRequest


def run_greenfield_test(test_case, routing_service):
    """Run a test case against the greenfield system."""
    try:
        graph = Graph.from_dict(test_case["graph"])
        
        request = RouteRequest(
            graph=graph,
            start=test_case["start"],
            goal=test_case["goal"],
            timeout_seconds=5.0
        )
        
        start_time = time.time()
        response = routing_service.route(request)
        elapsed_ms = (time.time() - start_time) * 1000
        
        return {
            "test_id": test_case["id"],
            "status": response.status.value,
            "path": response.path,
            "cost": response.cost,
            "time_ms": elapsed_ms,
            "algorithm": response.metadata.get("algorithm_used"),
            "error": response.error,
            "metadata": response.metadata
        }
    except Exception as e:
        return {
            "test_id": test_case["id"],
            "status": "exception",
            "path": None,
            "cost": None,
            "time_ms": 0,
            "algorithm": None,
            "error": str(e),
            "metadata": {}
        }


def main():
    """Run all test cases against greenfield system."""
    print("Running Greenfield System Tests...")
    print("=" * 60)
    
    routing_service = RoutingService()
    
    # Load test data
    test_data_path = Path(__file__).parent.parent / "data" / "test_data.json"
    with open(test_data_path, "r") as f:
        test_data = json.load(f)
    
    results = []
    for test_case in test_data["test_cases"]:
        print(f"\nTest: {test_case['id']}")
        result = run_greenfield_test(test_case, routing_service)
        results.append(result)
        
        if result["status"] == "success":
            print(f"  ✓ Path: {result['path']}, Cost: {result['cost']}, Algo: {result['algorithm']}")
        else:
            print(f"  ⚠ Status: {result['status']}, Error: {result.get('error', 'N/A')}")
    
    # Save results
    results_path = Path(__file__).parent.parent / "results" / "results_post.json"
    results_path.parent.mkdir(exist_ok=True)
    
    output = {
        "system": "greenfield",
        "version": "2.0.0",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r["status"] == "success"),
            "validation_errors": sum(1 for r in results if r["status"] == "validation_error"),
            "negative_cycles": sum(1 for r in results if r["status"] == "negative_cycle"),
            "no_path": sum(1 for r in results if r["status"] == "no_path"),
            "timeouts": sum(1 for r in results if r["status"] == "timeout"),
            "avg_time_ms": sum(r["time_ms"] for r in results) / len(results) if results else 0
        }
    }
    
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print("\n" + "=" * 60)
    print(f"\nResults saved to: {results_path}")
    print(f"Summary: {output['summary']['success']}/{output['summary']['total']} successful")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
