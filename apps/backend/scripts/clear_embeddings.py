from app.config import settings
from supabase import create_client

sb = create_client(settings.supabase_url, settings.supabase_key_resolved)

# Delete in batches of 500
batch_size = 500
total_deleted = 0

while True:
    # Get a batch of IDs
    resp = sb.table("catalog_embeddings").select("dataset_id").limit(batch_size).execute()
    ids = [r["dataset_id"] for r in resp.data]
    if not ids:
        break
    sb.table("catalog_embeddings").delete().in_("dataset_id", ids).execute()
    total_deleted += len(ids)
    print(f"Deleted {total_deleted}...")

print(f"Done. Total deleted: {total_deleted}")
