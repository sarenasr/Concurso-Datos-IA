-- 005_fix_embedding_dim.sql — bump catalog_embeddings.embedding from vector(768) to vector(1024).
--
-- Idempotent: checks the current column type before doing anything. Run AFTER
-- 002_embeddings.sql (which creates the table at 768). After this migration you
-- MUST re-run `scripts/build_embeddings` because all existing 768-dim vectors
-- are discarded (there is no loss-less 768->1024 cast for pgvector).

-- Drop the ivfflat index first (cannot ALTER column while an ivfflat index depends on it).
drop index if exists catalog_embeddings_embedding_idx;

-- Wipe existing 768-dim vectors — they cannot be cast to 1024.
-- (Will be re-embedded by scripts/build_embeddings.)
truncate table catalog_embeddings;

-- Bump the column dimension. Use DO block to be idempotent: only run if
-- the current type is vector(768). pgvector stores the dimension in atttypmod.
do $$
declare
  current_typmod int;
begin
  select a.atttypmod into current_typmod
  from pg_attribute a
  where a.attrelid = 'public.catalog_embeddings'::regclass
    and a.attname = 'embedding';
  if current_typmod is not null and current_typmod = 768 then
    alter table catalog_embeddings
      alter column embedding type vector(1024);
  end if;
end;
$$;

-- Recreate the ivfflat index at the new dimension.
create index if not exists catalog_embeddings_embedding_idx
  on catalog_embeddings using ivfflat (embedding vector_cosine_ops) with (lists = 100);
