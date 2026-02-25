from app.connectors.base_connector import BaseConnector, ConnectorType
from app.connectors.postgresql.connector import PostgreSQLConnector

# Registry of connector classes by type
_CONNECTOR_CLASSES: dict[ConnectorType, type[BaseConnector]] = {
    ConnectorType.POSTGRESQL: PostgreSQLConnector,
}

# Lazy-register BigQuery only when google-cloud-bigquery is installed
try:
    from app.connectors.bigquery.connector import BigQueryConnector

    _CONNECTOR_CLASSES[ConnectorType.BIGQUERY] = BigQueryConnector
except ImportError:
    pass

# Lazy-register Databricks only when databricks-sql-connector is installed
try:
    from app.connectors.databricks.connector import DatabricksConnector

    _CONNECTOR_CLASSES[ConnectorType.DATABRICKS] = DatabricksConnector
except ImportError:
    pass

# Cache of active connector instances by connection ID
_active_connectors: dict[str, BaseConnector] = {}


def get_connector_class(connector_type: str) -> type[BaseConnector]:
    """Get the connector class for a given type string."""
    try:
        ct = ConnectorType(connector_type)
    except ValueError:
        raise ValueError(
            f"Unknown connector type: {connector_type}. "
            f"Available: {[t.value for t in ConnectorType]}"
        )
    cls = _CONNECTOR_CLASSES.get(ct)
    if cls is None:
        raise ValueError(f"Connector type '{connector_type}' is not yet implemented.")
    return cls


def register_connector(connector_type: ConnectorType, cls: type[BaseConnector]) -> None:
    """Register a new connector class (plugin system)."""
    _CONNECTOR_CLASSES[connector_type] = cls


async def get_or_create_connector(
    connection_id: str,
    connector_type: str,
    connection_string: str,
) -> BaseConnector:
    """Get a cached connector or create a new one."""
    if connection_id in _active_connectors:
        connector = _active_connectors[connection_id]
        if await connector.test_connection():
            return connector
        # Connection is stale, remove it
        await connector.disconnect()
        del _active_connectors[connection_id]

    cls = get_connector_class(connector_type)
    connector = cls()
    await connector.connect(connection_string)
    _active_connectors[connection_id] = connector
    return connector


async def remove_connector(connection_id: str) -> None:
    """Disconnect and remove a cached connector."""
    if connection_id in _active_connectors:
        await _active_connectors[connection_id].disconnect()
        del _active_connectors[connection_id]
