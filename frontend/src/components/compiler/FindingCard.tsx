import { useState } from 'react';
import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Code,
  Collapse,
  Group,
  Progress,
  Stack,
  Table,
  Text,
  Tooltip,
} from '@mantine/core';
import { IconCheck, IconChevronDown, IconChevronRight, IconX } from '@tabler/icons-react';
import type { CompilationFinding } from '../../types/api';

const SOURCE_LABEL: Record<string, string> = {
  naming: 'Naming',
  value_overlap: 'Data probe',
  query_logs: 'Query logs',
  pg_stats: 'Statistics',
  constraint: 'Constraint',
  view: 'View',
  heuristic: 'Heuristic',
};

function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'green';
  if (confidence >= 0.6) return 'yellow';
  return 'orange';
}

interface DictionaryEntryPayload {
  raw_value: string;
  display_value: string;
}

interface FindingPayload {
  // metric
  sql_expression?: string;
  description?: string;
  dimensions?: string[];
  filters?: { where?: string };
  // glossary
  definition?: string;
  // dictionary
  entries?: DictionaryEntryPayload[];
  // relationship
  source_table?: string;
  source_column?: string;
  target_table?: string;
  target_column?: string;
  cardinality?: string | null;
  // policies / dead table / fanout
  column?: string;
  tables?: string[];
  masked_column?: string;
  category?: string;
  table?: string;
  guidance?: string;
}

function PayloadSummary({ finding }: { finding: CompilationFinding }) {
  const p = finding.payload as FindingPayload;
  switch (finding.kind) {
    case 'metric':
      return (
        <Stack gap={4}>
          <Code block>{String(p.sql_expression ?? '')}</Code>
          {p.description ? <Text size="sm">{String(p.description)}</Text> : null}
          <Text size="xs" c="dimmed">
            {p.dimensions?.length ? `Dimensions: ${p.dimensions.join(', ')}` : ''}
            {p.filters?.where ? `  ·  Filter: ${String(p.filters.where)}` : ''}
          </Text>
        </Stack>
      );
    case 'glossary':
      return <Text size="sm">{String(p.definition ?? '')}</Text>;
    case 'dictionary':
      return (
        <Table withTableBorder={false} verticalSpacing={2} fz="sm" w="auto">
          <Table.Tbody>
            {p.entries?.slice(0, 8).map(e => (
              <Table.Tr key={String(e.raw_value)}>
                <Table.Td>
                  <Code>{String(e.raw_value)}</Code>
                </Table.Td>
                <Table.Td>{String(e.display_value)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      );
    case 'relationship':
      return (
        <Text size="sm">
          <Code>
            {String(p.source_table)}.{String(p.source_column)}
          </Code>{' '}
          →{' '}
          <Code>
            {String(p.target_table)}.{String(p.target_column)}
          </Code>
          {p.cardinality ? (
            <Badge ml="xs" size="sm" variant="light">
              {String(p.cardinality)}
            </Badge>
          ) : null}
        </Text>
      );
    case 'data_policy_row_filter':
      return (
        <Stack gap={4}>
          <Text size="sm">
            Scoping column <Code>{String(p.column)}</Code> on {p.tables?.length ?? 0} tables.
            Accepting creates a <b>disabled</b> row-filter policy — edit the{' '}
            <Code>:tenant_id</Code> placeholder before enabling.
          </Text>
        </Stack>
      );
    case 'data_policy_masking':
      return (
        <Text size="sm">
          Mask <Code>{String(p.masked_column)}</Code> ({String(p.category)}). Merged into the
          “Compiler: PII masking” policy (created disabled).
        </Text>
      );
    case 'dead_table':
      return (
        <Text size="sm">
          Block <Code>{String(p.table)}</Code> from queries (merged into the “Compiler: dead
          tables” policy, created disabled).
        </Text>
      );
    case 'fanout_warning':
      return <Text size="sm">{String(p.guidance ?? '')}</Text>;
    default:
      return <Code block>{JSON.stringify(p, null, 2)}</Code>;
  }
}

interface FindingCardProps {
  finding: CompilationFinding;
  onAccept: (id: string) => void;
  onDismiss: (id: string) => void;
  busy?: boolean;
}

export function FindingCard({ finding, onAccept, onDismiss, busy }: FindingCardProps) {
  const [showEvidence, setShowEvidence] = useState(false);
  const reviewed = finding.status !== 'proposed';

  return (
    <Card withBorder padding="sm" radius="md" opacity={reviewed ? 0.6 : 1}>
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Group gap="xs" wrap="nowrap">
            <Text fw={600} size="sm" truncate>
              {finding.title}
            </Text>
            {reviewed && (
              <Badge size="sm" color={finding.status === 'accepted' ? 'green' : 'gray'}>
                {finding.status}
              </Badge>
            )}
          </Group>
          <PayloadSummary finding={finding} />
          <Group gap="xs">
            <Tooltip label={`Confidence ${(finding.confidence * 100).toFixed(0)}%`}>
              <Progress
                value={finding.confidence * 100}
                color={confidenceColor(finding.confidence)}
                w={90}
                size="sm"
              />
            </Tooltip>
            <Button
              variant="subtle"
              size="compact-xs"
              color="gray"
              leftSection={
                showEvidence ? <IconChevronDown size={12} /> : <IconChevronRight size={12} />
              }
              onClick={() => setShowEvidence(o => !o)}
            >
              {finding.evidence.length} evidence
            </Button>
          </Group>
          <Collapse in={showEvidence}>
            <Stack gap={2} pl="xs">
              {finding.evidence.map((e, i) => (
                <Group key={i} gap={6} wrap="nowrap">
                  <Badge size="xs" variant="outline" color="gray">
                    {SOURCE_LABEL[e.source] ?? e.source}
                  </Badge>
                  <Text size="xs" c="dimmed">
                    {e.detail}
                  </Text>
                </Group>
              ))}
            </Stack>
          </Collapse>
        </Stack>
        {!reviewed && (
          <Group gap={4} wrap="nowrap">
            <Tooltip label="Accept — creates a draft semantic object">
              <ActionIcon
                color="green"
                variant="light"
                disabled={busy}
                onClick={() => onAccept(finding.id)}
              >
                <IconCheck size={16} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Dismiss">
              <ActionIcon
                color="gray"
                variant="light"
                disabled={busy}
                onClick={() => onDismiss(finding.id)}
              >
                <IconX size={16} />
              </ActionIcon>
            </Tooltip>
          </Group>
        )}
      </Group>
    </Card>
  );
}
