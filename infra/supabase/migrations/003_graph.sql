create table if not exists graph_nodes (
  id text primary key,
  type text,
  label text,
  dataset_id text,
  extra jsonb
);

create table if not exists graph_edges (
  id bigserial primary key,
  src text references graph_nodes(id) on delete cascade,
  dst text references graph_nodes(id) on delete cascade,
  type text,
  confidence real,
  extra jsonb
);

create index if not exists graph_edges_src_idx on graph_edges (src);
create index if not exists graph_edges_dst_idx on graph_edges (dst);
