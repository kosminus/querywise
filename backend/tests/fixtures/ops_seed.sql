-- ============================================================================
-- "opsdb" — a deliberately hostile operational-style database.
--
-- Exercises the semantic layer compiler against the pathologies that real
-- operational schemas exhibit and warehouses don't:
--   * NO foreign keys declared anywhere (joins must be inferred)
--   * tenant_id scoping column on most tables (row-filter policy signal)
--   * soft deletes via deleted_at (canonical-filter signal)
--   * int-coded status columns + id/code/label lookup tables (dictionary signal)
--   * PII columns with realistic value shapes (masking-policy signal)
--   * handwritten views encoding business logic (view -> metric signal)
--   * an append-only audit/event table and a dead *_bak table
--
-- Runs in the sample-db container after the IFRS 9 seed (mounted as
-- 20_ops_seed.sql). Creates a separate database so sampledb stays pristine.
-- ============================================================================

CREATE DATABASE opsdb OWNER sample;
\connect opsdb

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

SELECT setseed(0.42);

-- ---------------------------------------------------------------------------
-- Tables (no foreign keys, on purpose)
-- ---------------------------------------------------------------------------

CREATE TABLE tenants (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE customer_statuses (
    id INT PRIMARY KEY,
    code TEXT NOT NULL,
    label TEXT NOT NULL
);

CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    date_of_birth DATE,
    national_id TEXT,
    status INT NOT NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,
    discontinued_at TIMESTAMPTZ
);

CREATE TABLE order_statuses (
    id INT PRIMARY KEY,
    code TEXT NOT NULL,
    label TEXT NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status INT NOT NULL,
    order_date DATE NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE payments (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    method INT NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL
);

-- Append-only audit table: high churn, polymorphic refs, never joined in views.
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Dead table: schema copy of customers, zero rows.
CREATE TABLE customers_bak (
    id BIGINT,
    tenant_id BIGINT,
    full_name TEXT,
    email TEXT,
    phone TEXT,
    date_of_birth DATE,
    national_id TEXT,
    status INT,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- Seed data
-- ---------------------------------------------------------------------------

INSERT INTO tenants (id, name)
SELECT i, 'Tenant ' || chr(64 + i::int)
FROM generate_series(1, 5) AS i;

INSERT INTO customer_statuses (id, code, label) VALUES
    (1, 'ACTIVE', 'Active'),
    (2, 'INACTIVE', 'Inactive'),
    (3, 'SUSPENDED', 'Suspended'),
    (4, 'CLOSED', 'Closed');

INSERT INTO order_statuses (id, code, label) VALUES
    (1, 'PENDING', 'Pending'),
    (2, 'PAID', 'Paid'),
    (3, 'COMPLETED', 'Completed'),
    (4, 'CANCELLED', 'Cancelled');

INSERT INTO customers (id, tenant_id, full_name, email, phone, date_of_birth,
                       national_id, status, deleted_at, created_at)
SELECT
    i,
    1 + (i % 5),
    'Customer ' || i,
    'customer' || i || '@example.com',
    '+1-555-' || lpad((1000 + i)::text, 4, '0'),
    DATE '1955-01-01' + (random() * 15000)::int,
    lpad((100000000 + i * 37)::text, 9, '0'),
    CASE WHEN random() < 0.70 THEN 1
         WHEN random() < 0.55 THEN 2
         WHEN random() < 0.50 THEN 3
         ELSE 4 END,
    CASE WHEN random() < 0.10 THEN now() - (random() * 200 || ' days')::interval END,
    now() - (random() * 900 || ' days')::interval
FROM generate_series(1, 200) AS i;

INSERT INTO products (id, sku, name, category, unit_price, discontinued_at)
SELECT
    i,
    'SKU-' || lpad(i::text, 5, '0'),
    'Product ' || i,
    (ARRAY['electronics', 'apparel', 'home', 'sports', 'grocery'])[1 + (i % 5)],
    round((5 + random() * 495)::numeric, 2),
    CASE WHEN random() < 0.08 THEN now() - (random() * 400 || ' days')::interval END
FROM generate_series(1, 40) AS i;

INSERT INTO orders (id, tenant_id, customer_id, status, order_date, total_amount,
                    deleted_at, created_at)
SELECT
    i,
    1 + (i % 5),
    1 + (i * 7) % 200,
    CASE WHEN random() < 0.10 THEN 1
         WHEN random() < 0.25 THEN 2
         WHEN random() < 0.85 THEN 3
         ELSE 4 END,
    DATE '2024-01-01' + (random() * 520)::int,
    round((10 + random() * 1990)::numeric, 2),
    CASE WHEN random() < 0.03 THEN now() - (random() * 100 || ' days')::interval END,
    now() - (random() * 500 || ' days')::interval
FROM generate_series(1, 2000) AS i;

INSERT INTO order_items (id, order_id, product_id, quantity, unit_price)
SELECT
    i,
    1 + (i % 2000),
    1 + (i * 13) % 40,
    1 + (random() * 4)::int,
    round((5 + random() * 495)::numeric, 2)
FROM generate_series(1, 6000) AS i;

INSERT INTO payments (id, order_id, amount, method, paid_at)
SELECT
    o.id,
    o.id,
    o.total_amount,
    CASE WHEN random() < 0.55 THEN 1 WHEN random() < 0.75 THEN 2 ELSE 3 END,
    o.order_date::timestamptz + interval '1 day'
FROM orders o
WHERE o.status IN (2, 3);

INSERT INTO events (tenant_id, entity_type, entity_id, event_type, payload, created_at)
SELECT
    1 + (i % 5),
    CASE WHEN i % 3 = 0 THEN 'customer' ELSE 'order' END,
    1 + (i % 2000),
    (ARRAY['created', 'updated', 'status_changed', 'deleted'])[1 + (i % 4)],
    jsonb_build_object('source', 'ops', 'seq', i),
    now() - (random() * 300 || ' days')::interval
FROM generate_series(1, 3000) AS i;

-- ---------------------------------------------------------------------------
-- Views: crystallized business logic (the compiler's richest evidence)
-- ---------------------------------------------------------------------------

CREATE VIEW v_active_customers AS
SELECT id, tenant_id, full_name, email, status, created_at
FROM customers
WHERE deleted_at IS NULL AND status = 1;

CREATE VIEW v_monthly_revenue AS
SELECT
    tenant_id,
    date_trunc('month', order_date) AS month,
    SUM(total_amount) AS revenue,
    COUNT(*) AS order_count
FROM orders
WHERE deleted_at IS NULL AND status = 3
GROUP BY tenant_id, date_trunc('month', order_date);

CREATE VIEW v_customer_order_counts AS
SELECT
    c.id AS customer_id,
    c.tenant_id,
    c.full_name,
    COUNT(o.id) AS order_count,
    SUM(o.total_amount) AS lifetime_value
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id AND o.deleted_at IS NULL
WHERE c.deleted_at IS NULL
GROUP BY c.id, c.tenant_id, c.full_name;

-- Populate pg_stats (most_common_vals etc.) — collectors are blind without this.
ANALYZE;
