-- Remove non-queryable catalog assets (charts, maps, stories, etc.) that were
-- indexed before the ingestion filter was added. Deleting from catalog cascades
-- to catalog_embeddings because of the foreign key.

delete from catalog
where type is null or type != 'dataset';
