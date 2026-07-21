"""Inspect current Supabase state for migration planning."""

from supabase import create_client
from app.config import settings

sb = create_client(settings.supabase_url, settings.supabase_key_resolved)

# Catalog count
cat = sb.table("catalog").select("id", count="exact").limit(1).execute()
print(f"catalog rows: {cat.count}")

# Embeddings count
emb = sb.table("catalog_embeddings").select("dataset_id", count="exact").limit(1).execute()
print(f"catalog_embeddings rows: {emb.count}")

# Sample embedding dimension
sample = sb.table("catalog_embeddings").select("embedding").limit(1).execute().data
if sample:
    raw = sample[0].get("embedding")
    if isinstance(raw, str):
        import ast

        vec = ast.literal_eval(raw)
        print(f"sample embedding dim: {len(vec)}")
    elif isinstance(raw, list):
        print(f"sample embedding dim: {len(raw)}")
    else:
        print(f"sample embedding type: {type(raw).__name__}, preview: {str(raw)[:80]}")
else:
    print("no embeddings to sample")

# Check if match_catalog function exists by trying to call it with zero-length vector
# (will fail with a specific error if function does NOT exist: "Could not find the function...")
print("\n--- probing match_catalog RPC ---")
try:
    # Use a 1024-dim zero vector stub
    zero_vec = str([0.0] * 1024)
    r = sb.rpc("match_catalog", {"qvec": zero_vec, "k": 1}).execute()
    print(f"RPC OK, returned {len(r.data)} rows; sample: {r.data[:1]}")
except Exception as e:
    msg = str(e)
    if "Could not find the function" in msg or "match_catalog" in msg:
        print(f"match_catalog NOT defined: {msg[:200]}")
    elif "vector" in msg.lower() and "dim" in msg.lower():
        print(f"match_catalog EXISTS but dimension mismatch: {msg[:200]}")
    else:
        print(f"match_catalog call error: {msg[:200]}")
