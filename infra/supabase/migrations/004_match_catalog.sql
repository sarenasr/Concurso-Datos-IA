-- match_catalog: approximate nearest-neighbour search over the catalog embeddings.
--
-- Uses pgvector cosine distance (operator <=>) with the vector_cosine_ops index.
-- The query vector `qvec` MUST be 1024-dimensional (matching google/gemini-embedding-2).
-- Returns cosine similarity (1 - distance) as `score` in [0, 1].
-- When `sector` is non-null, results are filtered to that domain_category.

create or replace function match_catalog(
  qvec vector,
  k int,
  sector text default null
)
returns table (
  id text,
  name text,
  description text,
  domain_category text,
  permalink text,
  page_views_last_month bigint,
  score float8
)
language plpgsql
stable
as $$
begin
  return query
  select
    c.id,
    c.name,
    c.description,
    c.domain_category,
    c.permalink,
    c.page_views_last_month,
    (1 - (e.embedding <=> qvec))::float8 as score
  from catalog_embeddings e
  join catalog c on c.id = e.dataset_id
  where c.type = 'dataset'
    and (sector is null or c.domain_category = sector)
  order by e.embedding <=> qvec
  limit k;
end;
$$;
