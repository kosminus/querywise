"""sqlglot-based SQL analysis for the compiler.

Richer than ``lineage_service.extract_refs`` (which only yields table/column
refs): extracts equi-join pairs, WHERE-clause columns, aggregate select items,
and GROUP BY dimensions. Like the lineage service, degrades gracefully —
returns ``None`` when sqlglot is unavailable or the statement doesn't parse.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JoinPair:
    left_table: str
    left_column: str
    right_table: str
    right_column: str

    def key(self) -> tuple[tuple[str, str], tuple[str, str]]:
        """Direction-insensitive identity for co-occurrence matching."""
        sides = sorted([(self.left_table, self.left_column), (self.right_table, self.right_column)])
        return (sides[0], sides[1])


@dataclass
class AggregateItem:
    sql: str  # rendered aggregate expression, e.g. "SUM(orders.total_amount)"
    function: str  # sum | count | avg | min | max | ...
    column: str | None  # "table.column" when resolvable
    alias: str | None = None


@dataclass
class SqlAnalysis:
    tables: list[str] = field(default_factory=list)  # real table names, lowercase
    join_pairs: list[JoinPair] = field(default_factory=list)
    where_columns: list[str] = field(default_factory=list)  # "table.column" or bare "column"
    where_sql: str | None = None
    aggregates: list[AggregateItem] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)


def analyze(sql: str, dialect: str | None = None) -> SqlAnalysis | None:
    """Parse one statement and extract compiler-relevant structure.

    Returns None if sqlglot is missing or parsing fails — callers treat the
    statement as opaque rather than erroring.
    """
    if not sql or not sql.strip():
        return None
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        logger.debug("sqlglot not installed; skipping SQL analysis")
        return None

    try:
        tree = sqlglot.parse_one(sql, dialect=dialect)
    except Exception as exc:
        logger.debug("sql analysis parse failed: %s", exc)
        return None

    # alias (or bare name) -> real table name, all lowercased
    alias_to_table: dict[str, str] = {}
    for table_node in tree.find_all(exp.Table):
        name = table_node.name.lower()
        alias_to_table[name] = name
        alias = table_node.alias
        if alias:
            alias_to_table[alias.lower()] = name
    tables = sorted(set(alias_to_table.values()))
    only_table = tables[0] if len(tables) == 1 else None

    def resolve(col: exp.Column) -> tuple[str | None, str]:
        qualifier = col.table.lower() if col.table else None
        if qualifier:
            return alias_to_table.get(qualifier, qualifier), col.name.lower()
        return only_table, col.name.lower()

    def dotted(col: exp.Column) -> str:
        table, name = resolve(col)
        return f"{table}.{name}" if table else name

    # --- equi-join pairs: any column = column across two different tables ---
    join_pairs: list[JoinPair] = []
    seen_pairs: set[tuple] = set()
    for eq in tree.find_all(exp.EQ):
        left, right = eq.this, eq.expression
        if not (isinstance(left, exp.Column) and isinstance(right, exp.Column)):
            continue
        lt, lc = resolve(left)
        rt, rc = resolve(right)
        if not lt or not rt or lt == rt:
            continue
        pair = JoinPair(lt, lc, rt, rc)
        if pair.key() not in seen_pairs:
            seen_pairs.add(pair.key())
            join_pairs.append(pair)

    # --- WHERE columns + rendered WHERE text (outermost only) ---
    where_columns: list[str] = []
    where_sql: str | None = None
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    where = select.args.get("where") if select is not None else None
    if where is not None:
        where_sql = where.this.sql(dialect=dialect)
        seen_cols: set[str] = set()
        for col in where.find_all(exp.Column):
            ref = dotted(col)
            if ref not in seen_cols:
                seen_cols.add(ref)
                where_columns.append(ref)

    # --- aggregates in the outermost projection ---
    aggregates: list[AggregateItem] = []
    if select is not None:
        for projection in select.expressions:
            alias = projection.alias if isinstance(projection, exp.Alias) else None
            for agg in projection.find_all(exp.AggFunc):
                inner_col = agg.find(exp.Column)
                aggregates.append(
                    AggregateItem(
                        sql=agg.sql(dialect=dialect),
                        function=agg.sql_name().lower(),
                        column=dotted(inner_col) if inner_col is not None else None,
                        alias=alias,
                    )
                )

    # --- GROUP BY dimensions ---
    group_by: list[str] = []
    if select is not None:
        group = select.args.get("group")
        if group is not None:
            for g in group.expressions:
                if isinstance(g, exp.Column):
                    group_by.append(dotted(g))
                else:
                    group_by.append(g.sql(dialect=dialect))

    return SqlAnalysis(
        tables=tables,
        join_pairs=join_pairs,
        where_columns=where_columns,
        where_sql=where_sql,
        aggregates=aggregates,
        group_by=group_by,
    )
