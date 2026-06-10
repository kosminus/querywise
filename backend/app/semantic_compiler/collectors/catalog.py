"""Catalog collector: maps connector introspection output to TableProfiles.

Takes duck-typed objects shaped like ``app.connectors.base_connector.TableInfo``
(schema_name, table_name, table_type, comment, row_count_estimate, columns[],
foreign_keys[]) so this package stays free of app imports.
"""

from typing import Any

from app.semantic_compiler.types import ColumnProfile, DeclaredFK, TableProfile


def build_table_profiles(table_infos: list[Any]) -> list[TableProfile]:
    profiles: list[TableProfile] = []
    for info in table_infos:
        columns = [
            ColumnProfile(
                name=col.name,
                data_type=col.data_type,
                is_nullable=col.is_nullable,
                is_primary_key=col.is_primary_key,
                comment=col.comment,
                ordinal_position=col.ordinal_position,
            )
            for col in info.columns
        ]
        fks = [
            DeclaredFK(
                source_column=fk.column_name,
                target_schema=fk.referred_schema,
                target_table=fk.referred_table,
                target_column=fk.referred_column,
            )
            for fk in info.foreign_keys
        ]
        profiles.append(
            TableProfile(
                schema_name=info.schema_name,
                table_name=info.table_name,
                table_type=info.table_type,
                comment=info.comment,
                row_count_estimate=info.row_count_estimate,
                columns=columns,
                declared_fks=fks,
            )
        )
    return profiles
