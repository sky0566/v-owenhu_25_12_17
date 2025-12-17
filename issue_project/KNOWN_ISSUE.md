# Known Issue: Dijkstra on Negative Weights

**Type:** Missing input validation / incorrect algorithm choice

**Symptom:** `dijkstra_shortest_path` returns the non-optimal route `A→B` (cost 5) instead of `A→C→D→F→B` (cost 1) because it runs Dijkstra on a graph containing a negative edge `D→F = -3`.

**Root Cause:**
- No validation rejects graphs with negative weights before invoking Dijkstra.
- Implementation marks nodes as visited upon discovery, preventing later relaxations that would yield a cheaper path.

**Trigger:** Load `data/graph_negative_weight.json` and route `A` to `B`.

**Expected Behavior:**
- Either raise an error when negative weights are present, **or** use Bellman-Ford (or another algorithm supporting negative edges) to compute the correct shortest path (total cost 1).

**Fix implemented:**
- Scan edges for `weight < 0` before running Dijkstra; `dijkstra_shortest_path` now raises `ValueError` with a message containing "negative" if any negative-weight edges are found.
- Corrected Dijkstra implementation to mark nodes as finalized when popped from the heap (no premature finalization).
- Added `bellman_ford_shortest_path` to compute shortest paths on graphs with negative weights and detect negative-weight cycles.

Unit tests were updated to assert the new behavior: Dijkstra rejects negative-weight graphs while Bellman-Ford returns the optimal path for the provided fixture.
