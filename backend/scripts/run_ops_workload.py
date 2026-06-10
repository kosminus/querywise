"""Run a representative query workload against the opsdb fixture.

Populates pg_stat_statements so the semantic layer compiler's query-log
collector has evidence to mine: join co-occurrence (orders <-> customers,
order_items <-> orders, status lookups), tenant-scoped WHERE clauses on
nearly every query, and recurring aggregate shapes.

Usage (sample-db container must be up):
    python backend/scripts/run_ops_workload.py [--dsn DSN] [--rounds N]
"""

import argparse
import asyncio
import random

import asyncpg

DEFAULT_DSN = "postgresql://sample:sample_dev@localhost:5433/opsdb"

# Each shape is run every round with fresh literals. pg_stat_statements
# normalizes constants, so repeated shapes accumulate `calls`.
QUERY_SHAPES: list[str] = [
    # --- tenant-scoped single-table lookups (tenant ubiquity signal) ---
    "SELECT * FROM customers WHERE tenant_id = {t} AND deleted_at IS NULL LIMIT 50",
    "SELECT * FROM customers WHERE tenant_id = {t} AND status = {cs}",
    "SELECT * FROM orders WHERE tenant_id = {t} AND order_date >= DATE '2024-06-01'",
    "SELECT * FROM orders WHERE tenant_id = {t} AND status = {os} AND deleted_at IS NULL",
    "SELECT * FROM events WHERE tenant_id = {t} AND entity_type = 'order' LIMIT 100",
    "SELECT * FROM customers WHERE tenant_id = {t} AND email = 'customer{i}@example.com'",
    # --- joins (co-occurrence evidence; no FKs exist, logs are the proof) ---
    """SELECT c.full_name, o.id, o.total_amount
       FROM orders o JOIN customers c ON o.customer_id = c.id
       WHERE o.tenant_id = {t} AND o.deleted_at IS NULL LIMIT 100""",
    """SELECT o.id, SUM(oi.quantity * oi.unit_price) AS line_total
       FROM order_items oi JOIN orders o ON oi.order_id = o.id
       WHERE o.tenant_id = {t} GROUP BY o.id LIMIT 100""",
    """SELECT p.name, SUM(oi.quantity) AS units
       FROM order_items oi JOIN products p ON oi.product_id = p.id
       GROUP BY p.name ORDER BY units DESC LIMIT 20""",
    """SELECT o.id, pay.amount, pay.paid_at
       FROM payments pay JOIN orders pay_o ON pay.order_id = pay_o.id
       JOIN orders o ON o.id = pay_o.id WHERE o.tenant_id = {t} LIMIT 50""",
    """SELECT c.full_name, cs.label
       FROM customers c JOIN customer_statuses cs ON c.status = cs.id
       WHERE c.tenant_id = {t} LIMIT 50""",
    """SELECT o.id, os.label
       FROM orders o JOIN order_statuses os ON o.status = os.id
       WHERE o.tenant_id = {t} AND o.order_date >= DATE '2024-01-01' LIMIT 50""",
    """SELECT c.id, c.full_name, COUNT(o.id) AS n
       FROM customers c LEFT JOIN orders o ON o.customer_id = c.id
       WHERE c.tenant_id = {t} AND c.deleted_at IS NULL
       GROUP BY c.id, c.full_name ORDER BY n DESC LIMIT 25""",
    # --- recurring aggregates (metric candidates) ---
    """SELECT SUM(total_amount) FROM orders
       WHERE tenant_id = {t} AND status = 3 AND deleted_at IS NULL""",
    """SELECT date_trunc('month', order_date) AS m, SUM(total_amount)
       FROM orders WHERE tenant_id = {t} AND deleted_at IS NULL AND status = 3
       GROUP BY m ORDER BY m""",
    """SELECT status, COUNT(*) FROM orders
       WHERE tenant_id = {t} AND deleted_at IS NULL GROUP BY status""",
    """SELECT category, COUNT(*) FROM products GROUP BY category""",
    """SELECT AVG(total_amount) FROM orders
       WHERE tenant_id = {t} AND status = 3 AND deleted_at IS NULL""",
    """SELECT COUNT(*) FROM customers
       WHERE tenant_id = {t} AND status = 1 AND deleted_at IS NULL""",
    """SELECT method, SUM(amount) FROM payments GROUP BY method""",
    # --- view usage ---
    "SELECT * FROM v_monthly_revenue WHERE tenant_id = {t} ORDER BY month DESC LIMIT 12",
    "SELECT COUNT(*) FROM v_active_customers WHERE tenant_id = {t}",
    """SELECT * FROM v_customer_order_counts WHERE tenant_id = {t}
       ORDER BY lifetime_value DESC LIMIT 10""",
]


async def run(dsn: str, rounds: int) -> None:
    conn = await asyncpg.connect(dsn)
    rng = random.Random(42)
    executed = 0
    try:
        for _ in range(rounds):
            for shape in QUERY_SHAPES:
                sql = shape.format(
                    t=rng.randint(1, 5),
                    cs=rng.randint(1, 4),
                    os=rng.randint(1, 4),
                    i=rng.randint(1, 200),
                )
                await conn.fetch(sql)
                executed += 1
        await conn.execute("ANALYZE")
        tracked = await conn.fetchval(
            "SELECT count(*) FROM pg_stat_statements WHERE dbid = "
            "(SELECT oid FROM pg_database WHERE datname = current_database())"
        )
        print(f"Executed {executed} queries; pg_stat_statements now tracks {tracked} statements.")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=DEFAULT_DSN)
    parser.add_argument("--rounds", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(run(args.dsn, args.rounds))


if __name__ == "__main__":
    main()
