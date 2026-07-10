create table if not exists catalog_embeddings (
  dataset_id text primary key references catalog(id) on delete cascade,
  embedding vector(768),
  doc_text text,
  created_at timestamptz default now()
);

create index if not exists catalog_embeddings_embedding_idx
  on catalog_embeddings using ivfflat (embedding vector_cosine_ops) with (lists = 100);
