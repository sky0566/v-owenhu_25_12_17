# Logistics Routing (Intentional Negative-Weight Bug)

## Overview
This minimal Python module models a logistics routing script that **hard-codes Dijkstra** on a graph containing a **negative-weight edge**. The implementation intentionally **fails to validate** negative weights and prematurely marks nodes as visited, leading to suboptimal routes.

## Scenario
**Graph (directed):**
- A→B (5)
- A→C (2)
- C→D (1)
- D→F (**-3**)
- F→B (1)
- A→E (1)
- E→B (6)

**Expected:** Detect negative edge and reject (or switch to Bellman-Ford), or find shortest path `A→C→D→F→B` with total cost **1**.

**Actual (bug):** Returns `A→B` (5) or `A→E→B` (7), because Dijkstra is used despite a negative edge and nodes are marked visited too early.

## Project Structure
```
src/logistics/          # Core code
  graph.py              # Graph loader & helper
  routing.py            # Naive Dijkstra (buggy)
tests/                  # Automated tests (currently failing on purpose)
  test_routing_negative_weight.py
 data/                  # Sample graph data
  graph_negative_weight.json
README.md

This repo contains the legacy issue_project and an appointment_v2 greenfield replacement prototype.

To run the new scenario tests:

- From the repository root: ./run_all.sh
- Or run appointment_v2 directly: ./appointment_v2/run_tests.sh

Artifacts:
- appointment_v2/results/results_post.json: test metrics and outcomes
- appointment_v2/logs/log_schema.md: structured logging guidance
               # This file
requirements.txt        # Dependencies (pytest)
pytest.ini              # Pytest config (pythonpath=src)
KNOWN_ISSUE.md          # Root-cause summary and fix hints
```

## Quickstart (Windows PowerShell)
```powershell
# create and activate virtualenv, then install legacy and prototype deps
python -m venv .venv; .\.venv\Scripts\activate
# from the repo root, change into the project folder and install required deps
cd v-owenhu_25_12_17/issue_project
pip install -r requirements.txt
# optionally install appointment_v2 test deps
pip install -r appointment_v2/requirements.txt
pytest
```

## Sample Usage
```python
from logistics.graph import Graph
from logistics.routing import dijkstra_shortest_path

graph = Graph.from_json_file("data/graph_negative_weight.json")
path, cost = dijkstra_shortest_path(graph, "A", "B")
print(path, cost)  # BUG: likely ['A', 'B'] 5.0
```

## Notes
- Tests are expected to **fail** until negative-edge validation and a correct algorithm (e.g., Bellman-Ford) are implemented.
- Keeping the bug explicit helps demonstrate the importance of algorithm preconditions in route planning.
