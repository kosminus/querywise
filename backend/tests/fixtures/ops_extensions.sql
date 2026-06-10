-- Runs first (mounted as 05_extensions.sql). Requires the container to start
-- postgres with -c shared_preload_libraries=pg_stat_statements (see docker-compose.yml).
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
