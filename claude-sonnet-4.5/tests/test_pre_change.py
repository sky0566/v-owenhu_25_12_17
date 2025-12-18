"""
Legacy system baseline test runner.
Runs the original buggy implementation to establish baseline metrics.
"""

import sys
import json
import time
from pathlib import Path

# Add legacy project to path
LEGACY_PATH = Path(__file__).resolve().parents[2] / "issue_project"
sys.path.insert(0, str(LEGACY_PATH / "src"))

from logistics.graph import Graph
from logistics.routing import dijkstra_shortest_path


def run_legacy_test(test_case):
    """Run a test case against the legacy system."""
    try:
        graph = Graph.from_edge_list([
            (e["source"], e["target"], e["weight"])
            for e in test_case["graph"]["edges"]
        ])
        
        start_time = time.time()
        path, cost = dijkstra_shortest_path(
            graph,
            test_case["start"],
            test_case["goal"]
        )
        elapsed_ms = (time.time() - start_time) * 1000
        
        return {
            "test_id": test_case["id"],
            "status": "completed",
            "path": path,
            "cost": cost,
            "time_ms": elapsed_ms,
            "error": None
        }
    except Exception as e:
        return {
            "test_id": test_case["id"],
            "status": "error",
            "path": None,
            "cost": None,
            "time_ms": 0,
            "error": str(e)
        }


def main():
    """Run all test cases against legacy system."""
    print("Running Legacy System Baseline Tests...")
    print("=" * 60)
    
    # Load test data
    test_data_path = Path(__file__).parent.parent / "data" / "test_data.json"
    with open(test_data_path, "r") as f:
        test_data = json.load(f)
    
    results = []
    for test_case in test_data["test_cases"]:
        print(f"\nTest: {test_case['id']}")
        result = run_legacy_test(test_case)
        results.append(result)
        
        if result["status"] == "completed":
            print(f"  ✓ Path: {result['path']}, Cost: {result['cost']}")
        else:
            print(f"  ✗ Error: {result['error']}")
    
    # Save results
    results_path = Path(__file__).parent.parent / "results" / "results_pre.json"
    results_path.parent.mkdir(exist_ok=True)
    
    output = {
        "system": "legacy",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r["status"] == "completed"),
            "failed": sum(1 for r in results if r["status"] == "error"),
            "avg_time_ms": sum(r["time_ms"] for r in results) / len(results) if results else 0
        }
    }
    
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print("\n" + "=" * 60)
    print(f"\nResults saved to: {results_path}")
    print(f"Summary: {output['summary']['passed']}/{output['summary']['total']} passed")
    
    return 0 if output['summary']['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
