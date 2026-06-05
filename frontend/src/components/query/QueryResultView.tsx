import {
  Stack,
  Paper,
  Text,
  Table,
  Badge,
  Group,
  Accordion,
  Code,
  CopyButton,
  ActionIcon,
  Tooltip,
} from '@mantine/core';
import { IconCopy, IconCheck } from '@tabler/icons-react';
import type { QueryResult } from '../../types/api';

export function QueryResultView({ result }: { result: QueryResult }) {
  return (
    <Stack gap="md">
      {result.summary && (
        <Paper withBorder p="md" bg="blue.0">
          <Text fw={600} mb="xs">
            Summary
          </Text>
          <Text>{result.summary}</Text>
          {result.highlights.length > 0 && (
            <Group mt="xs" gap="xs">
              {result.highlights.map((h, i) => (
                <Badge key={i} variant="light">
                  {h}
                </Badge>
              ))}
            </Group>
          )}
        </Paper>
      )}

      <Accordion variant="contained">
        <Accordion.Item value="sql">
          <Accordion.Control>
            <Group>
              <Text fw={500}>SQL</Text>
              <Badge size="sm" variant="light">
                {result.execution_time_ms}ms
              </Badge>
              <Badge size="sm" variant="light" color="gray">
                {result.row_count} rows
              </Badge>
              {result.retry_count > 0 && (
                <Badge size="sm" color="yellow">
                  {result.retry_count} retries
                </Badge>
              )}
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <Group justify="flex-end" mb="xs">
              <CopyButton value={result.final_sql}>
                {({ copied, copy }) => (
                  <Tooltip label={copied ? 'Copied' : 'Copy'}>
                    <ActionIcon variant="subtle" onClick={copy}>
                      {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                    </ActionIcon>
                  </Tooltip>
                )}
              </CopyButton>
            </Group>
            <Code block>{result.final_sql}</Code>
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>

      {result.rows.length > 0 && (
        <Paper withBorder>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                {result.columns.map((col) => (
                  <Table.Th key={col}>{col}</Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {result.rows.map((row, i) => (
                <Table.Tr key={i}>
                  {row.map((cell, j) => (
                    <Table.Td key={j}>
                      {cell === null ? (
                        <Text c="dimmed" fs="italic" size="sm">
                          null
                        </Text>
                      ) : (
                        String(cell)
                      )}
                    </Table.Td>
                  ))}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          {result.truncated && (
            <Text size="sm" c="dimmed" ta="center" py="xs">
              Results truncated to {result.row_count} rows
            </Text>
          )}
        </Paper>
      )}

      {result.suggested_followups.length > 0 && (
        <Paper withBorder p="md">
          <Text fw={600} mb="xs">
            Suggested follow-up questions
          </Text>
          <Stack gap="xs">
            {result.suggested_followups.map((q, i) => (
              <Text key={i} size="sm" c="blue">
                {q}
              </Text>
            ))}
          </Stack>
        </Paper>
      )}
    </Stack>
  );
}
