create extension if not exists vector;

create table if not exists catalog (
  id text primary key,
  name text,
  description text,
  type text,
  domain_category text,
  domain_tags text[],
  domain_metadata jsonb,
  columns_name text[],
  columns_field_name text[],
  columns_datatype text[],
  columns_description text[],
  page_views_last_week bigint,
  page_views_last_month bigint,
  page_views_total bigint,
  download_count bigint,
  permalink text,
  updated_at timestamptz,
  created_at timestamptz default now()
);

create index if not exists catalog_domain_category_idx on catalog (domain_category);
