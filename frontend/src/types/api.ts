export interface Connection {
  id: string;
  name: string;
  connector_type: string;
  default_schema: string;
  max_query_timeout_seconds: number;
  max_rows: number;
  is_active: boolean;
  has_connection_string: boolean;
  last_introspected_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectionCreate {
  name: string;
  connector_type: string;
  connection_string: string;
  default_schema: string;
  max_query_timeout_seconds: number;
  max_rows: number;
}

export interface TableSummary {
  id: string;
  schema_name: string;
  table_name: string;
  table_type: string;
  comment: string | null;
  row_count_estimate: number | null;
  column_count: number;
  created_at: string;
}

export interface Column {
  id: string;
  column_name: string;
  data_type: string;
  is_nullable: boolean;
  is_primary_key: boolean;
  default_value: string | null;
  comment: string | null;
  ordinal_position: number;
}

export interface Relationship {
  constraint_name: string | null;
  source_table: string;
  source_column: string;
  target_table: string;
  target_column: string;
}

export interface TableDetail {
  id: string;
  schema_name: string;
  table_name: string;
  table_type: string;
  comment: string | null;
  row_count_estimate: number | null;
  columns: Column[];
  outgoing_relationships: Relationship[];
  incoming_relationships: Relationship[];
}

export interface GlossaryTerm {
  id: string;
  connection_id: string;
  term: string;
  definition: string;
  sql_expression: string;
  related_tables: string[] | null;
  related_columns: string[] | null;
  examples: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface MetricDefinition {
  id: string;
  connection_id: string;
  metric_name: string;
  display_name: string;
  description: string | null;
  sql_expression: string;
  aggregation_type: string | null;
  related_tables: string[] | null;
  dimensions: string[] | null;
  filters: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface DictionaryEntry {
  id: string;
  column_id: string;
  raw_value: string;
  display_value: string;
  description: string | null;
  sort_order: number;
  created_at: string;
}

export interface QueryResult {
  id: string;
  question: string;
  generated_sql: string;
  final_sql: string;
  explanation: string;
  columns: string[];
  column_types: string[];
  rows: unknown[][];
  row_count: number;
  execution_time_ms: number;
  truncated: boolean;
  summary: string | null;
  highlights: string[];
  suggested_followups: string[];
  llm_provider: string;
  llm_model: string;
  retry_count: number;
}

export interface QueryHistory {
  id: string;
  connection_id: string;
  natural_language: string;
  generated_sql: string | null;
  final_sql: string | null;
  execution_status: string;
  error_message: string | null;
  row_count: number | null;
  execution_time_ms: number | null;
  retry_count: number;
  result_summary: string | null;
  is_favorite: boolean;
  created_at: string;
}

export interface IntrospectionResult {
  tables_found: number;
  columns_found: number;
  relationships_found: number;
}

export interface KnowledgeDocument {
  id: string;
  connection_id: string;
  title: string;
  source_url: string | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeChunk {
  id: string;
  chunk_index: number;
  content: string;
  created_at: string;
}

export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  chunks: KnowledgeChunk[];
}
