import time

print("Starting agent test...", flush=True)
t0 = time.time()

from app.agents.tools import search_catalog  # noqa: E402

print(f"--- Test 1: search_catalog ({time.time() - t0:.1f}s) ---", flush=True)
results = search_catalog("contratos firmados Medellin 2025", k=3)
for r in results:
    name = (r.get("name") or "?")[:60]
    print(f"  {r['id']} | {name} | score={r.get('score', 0):.3f}")

print(f"\n--- Test 2: get_schema ({time.time() - t0:.1f}s) ---", flush=True)
from app.agents.tools import get_schema  # noqa: E402

if results:
    schema = get_schema(results[0]["id"])
    if schema:
        print(f"  {schema['id']}: {schema['name']} ({len(schema.get('columns', []))} cols)")
        for c in schema.get("columns", [])[:5]:
            print(f"    {c.get('field_name', '')} | {c.get('name', '')} | {c.get('datatype', '')}")

print(f"\n--- Test 3: query_dataset ({time.time() - t0:.1f}s) ---", flush=True)
from app.agents.tools import query_dataset  # noqa: E402

if results:
    r = query_dataset(results[0]["id"], "$select=count(*)")
    print(f"  rows: {r['rows']}")
    print(f"  count: {r['count']}")
    print(f"  error: {r['error']}")

print(f"\n--- Test 4: full agent ({time.time() - t0:.1f}s) ---", flush=True)
from app.agents.graph import run_agent  # noqa: E402

state = run_agent("Cuantos medicamentos vigentes hay registrados?")
print(f"  answer: {state.get('answer', 'NO ANSWER')}")
print(f"  soql: {state.get('soql', '')}")
print(f"  dataset: {state.get('dataset_id', '')}")
print(f"  sources: {state.get('sources', [])}")
print(f"  chart: {'yes' if state.get('chart') else 'no'}")
print(f"\nTotal time: {time.time() - t0:.1f}s")
