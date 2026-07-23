-- Full-text search over catalog name + description + domain_tags.
--
-- The keyword leg of hybrid retrieval previously matched only `name` via
-- ilike, so relevance hiding in the description or tags never surfaced.
-- This adds a generated `fts` tsvector (Spanish config) covering all three
-- fields, a GIN index on it, and a `match_catalog_text` RPC that ranks
-- datasets with `ts_rank`, mirroring the `match_catalog` vector RPC.
--
-- Idempotent: safe to re-run.

alter table catalog
  add column if not exists fts tsvector
  generated always as (
    to_tsvector(
      -- cast to regconfig: the text-literal form to_tsvector('spanish', ...)
      -- is only STABLE (runtime config lookup) and is rejected in a generated
      -- column; the regconfig overload is IMMUTABLE.
      'spanish'::regconfig,
      coalesce(name, '') || ' ' || coalesce(description, '') || ' ' ||
      array_to_string(coalesce(domain_tags, '{}'), ' ')
    )
  ) stored;

create index if not exists catalog_fts_idx on catalog using gin (fts);

create or replace function match_catalog_text(
  q text,
  k int
)
returns table (
  id text,
  name text,
  description text,
  domain_category text,
  permalink text,
  page_views_last_month bigint
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
    c.page_views_last_month
  from catalog c
  where c.type = 'dataset'
    and c.fts @@ websearch_to_tsquery('spanish', q)
  order by ts_rank(c.fts, websearch_to_tsquery('spanish', q)) desc
  limit k;
end;
$$;
