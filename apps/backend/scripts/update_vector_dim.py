from app.config import settings

# Parse the Supabase URL to get connection details
url = settings.supabase_url
# Extract password from service key JWT or use direct connection
# For now, use the service key to get connection info

# Actually, let's use the Supabase REST API to execute SQL via the pg-meta endpoint
# Or better, use the connection string from the environment

# The simplest approach: use the existing supabase client to check current schema
from supabase import create_client  # noqa: E402

sb = create_client(settings.supabase_url, settings.supabase_key_resolved)

# Check current column type
result = sb.table("catalog_embeddings").select("embedding").limit(1).execute()
print(f"Current embedding sample: {result.data}")

# We need to use the Supabase Management API or direct DB connection
# For now, let's just clear and re-embed with the new model
# The vector dimension will be updated when we insert new data

print(
    "Note: Vector column dimension needs to be updated via Supabase dashboard or direct DB access"
)
print("For now, clearing old embeddings and re-embedding with Cohere 1024-dim model")
