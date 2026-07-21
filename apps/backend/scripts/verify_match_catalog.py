"""End-to-end verification of the match_catalog RPC with a real Gemini embedding."""

from supabase import create_client
from app.config import settings
from app.rag.embeddings import embed_text
from app.rag.catalog import search_catalog


def main() -> None:
    q = "contratos públicos firmados en Medellín en 2025"
    print(f"query: {q}")
    vec = embed_text(q)
    print(f"embedding dim: {len(vec)}")

    sb = create_client(settings.supabase_url, settings.supabase_key_resolved)
    print("\n--- direct RPC match_catalog ---")
    rows = sb.rpc("match_catalog", {"qvec": str(vec), "k": 5}).execute().data
    for r in rows:
        print(f"  {r['id']}  score={r['score']:.3f}  {r['name'][:60]}")

    print("\n--- search_catalog (fused + reranker if enabled) ---")
    out = search_catalog(q, k=5)
    for r in out:
        print(
            f"  {r.get('id')}  score={float(r.get('score', 0)):.3f}  {(r.get('name') or '')[:60]}"
        )


if __name__ == "__main__":
    main()
