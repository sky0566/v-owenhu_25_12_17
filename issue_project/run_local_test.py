import sys
from pathlib import Path
# Ensure src is on sys.path so we can import the package during local runs
ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT / "src"))

from logistics.graph import Graph
from logistics.routing import dijkstra_shortest_path, bellman_ford_shortest_path

g = Graph.from_json_file('data/graph_negative_weight.json')
print('Testing dijkstra (should raise on negative weights)')
try:
    path, cost = dijkstra_shortest_path(g, 'A', 'B')
    print('DIJKSTRA OK', path, cost)
except Exception as e:
    print('DIJKSTRA ERR', type(e).__name__, e)

print('Testing bellman-ford (should find optimal path)')
try:
    path, cost = bellman_ford_shortest_path(g, 'A', 'B')
    print('BF OK', path, cost)
except Exception as e:
    print('BF ERR', type(e).__name__, e)