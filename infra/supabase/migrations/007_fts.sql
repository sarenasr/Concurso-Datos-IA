-- Full-text search over catalog name + description + domain_tags.
--
-- The keyword leg of hybrid retrieval previously matched only `name` via
-- ilike, so relevance hiding in the description or tags never surfaced.
-- This adds an `fts` tsvector (Spanish config) covering all three fields, a
-- GIN index on it, and a `match_catalog_text` RPC that ranks datasets with
-- `ts_rank`, mirroring the `match_catalog` vector RPC.
--
-- FIELD WEIGHTING: the tsvector is built with `setweight` so a term matching
-- the dataset NAME (weight A) ranks far above the same term buried in the
-- DESCRIPTION (weight B) or domain TAGS (weight C). Without this, broad FTS
-- matching floods the keyword leg — e.g. every dataset mentioning "contratos"
-- in its description ties with "SECOP II - Contratos" itself, burying the
-- exact-answer dataset below the candidate window. ts_rank respects these
-- weights (default {D,C,B,A} = {0.1, 0.2, 0.4, 1.0}).
--
-- We maintain `fts` with a BEFORE INSERT/UPDATE trigger rather than a
-- `generated always as (...)` column. A generated column requires its
-- expression to be IMMUTABLE, and Postgres is finicky about proving that for
-- to_tsvector even with the regconfig cast — the trigger approach sidesteps
-- the immutability check entirely and is the pattern Supabase documents.
--
-- Idempotent: safe to re-run.

-- Drop any partial state from earlier failed attempts, then add a plain column.
alter table catalog drop column if exists fts;
alter table catalog add column fts tsvector;

create or replace function catalog_fts_refresh()
returns trigger
language plpgsql
as $$
begin
  new.fts :=
    setweight(to_tsvector('spanish'::regconfig, coalesce(new.name, '')), 'A') ||
    setweight(to_tsvector('spanish'::regconfig, coalesce(new.description, '')), 'B') ||
    setweight(
      to_tsvector(
        'spanish'::regconfig,
        array_to_string(coalesce(new.domain_tags, '{}'), ' ')
      ),
      'C'
    );
  return new;
end;
$$;

drop trigger if exists catalog_fts_trg on catalog;
create trigger catalog_fts_trg
  before insert or update of name, description, domain_tags
  on catalog
  for each row
  execute function catalog_fts_refresh();

-- Backfill existing rows (the trigger only fires on future writes).
-- Must mirror the weighted expression in catalog_fts_refresh().
update catalog
  set fts =
    setweight(to_tsvector('spanish'::regconfig, coalesce(name, '')), 'A') ||
    setweight(to_tsvector('spanish'::regconfig, coalesce(description, '')), 'B') ||
    setweight(
      to_tsvector(
        'spanish'::regconfig,
        array_to_string(coalesce(domain_tags, '{}'), ' ')
      ),
      'C'
    );

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

-- Tell PostgREST to pick up the new function immediately.
notify pgrst, 'reload schema';
