import { useState } from 'react';
import {
  Stack,
  Title,
  Group,
  Text,
  Paper,
  SimpleGrid,
  Select,
  SegmentedControl,
  Table,
  Alert,
  Loader,
} from '@mantine/core';
import { useAuth } from '../context/auth';
import {
  useCostBy,
  useSlowestQueries,
  useTableUsage,
  useUsageSummary,
} from '../hooks/useAnalytics';

function formatBytes(n: number): string {
  if (!n) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(1)} ${units[i]}`;
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Paper withBorder p="md" radius="md">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="xl" fw={700}>
        {value}
      </Text>
    </Paper>
  );
}

export function AnalyticsPage() {
  const { role } = useAuth();
  const isAdmin = role === 'admin';
  const [days, setDays] = useState('30');
  const [by, setBy] = useState('workspace');
  const d = Number(days);

  const usage = useUsageSummary(d, isAdmin);
  const cost = useCostBy(by, d, isAdmin);
  const slowest = useSlowestQueries(d, isAdmin);
  const tables = useTableUsage(d, isAdmin);

  if (!isAdmin) {
    return (
      <Stack gap="md">
        <Title order={2}>Usage &amp; Cost</Title>
        <Alert color="yellow" title="Admins only">
          Usage analytics are restricted to workspace administrators.
        </Alert>
      </Stack>
    );
  }

  const s = usage.data;

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Usage &amp; Cost</Title>
        <Select
          w={160}
          value={days}
          onChange={(v) => v && setDays(v)}
          data={[
            { value: '7', label: 'Last 7 days' },
            { value: '30', label: 'Last 30 days' },
            { value: '90', label: 'Last 90 days' },
          ]}
        />
      </Group>

      {usage.isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      ) : (
        <SimpleGrid cols={{ base: 2, md: 5 }}>
          <StatCard label="Queries" value={String(s?.total_queries ?? 0)} />
          <StatCard
            label="Error rate"
            value={`${((s?.error_rate ?? 0) * 100).toFixed(1)}%`}
          />
          <StatCard label="Est. cost" value={`$${(s?.total_cost_usd ?? 0).toFixed(2)}`} />
          <StatCard label="Data scanned" value={formatBytes(s?.total_scanned_bytes ?? 0)} />
          <StatCard
            label="Avg latency"
            value={s?.avg_execution_ms != null ? `${Math.round(s.avg_execution_ms)} ms` : '—'}
          />
        </SimpleGrid>
      )}

      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="sm">
          <Text fw={600}>Cost attribution</Text>
          <SegmentedControl
            size="xs"
            value={by}
            onChange={setBy}
            data={[
              { value: 'workspace', label: 'Workspace' },
              { value: 'user', label: 'User' },
              { value: 'connection', label: 'Connection' },
            ]}
          />
        </Group>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{by}</Table.Th>
              <Table.Th>Queries</Table.Th>
              <Table.Th>Est. cost</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(cost.data ?? []).map((c) => (
              <Table.Tr key={c.key ?? 'none'}>
                <Table.Td>
                  <Text size="xs" ff="monospace">
                    {c.key ? c.key.slice(0, 8) : '—'}
                  </Text>
                </Table.Td>
                <Table.Td>{c.query_count}</Table.Td>
                <Table.Td>${c.cost_usd.toFixed(4)}</Table.Td>
              </Table.Tr>
            ))}
            {cost.data?.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={3}>
                  <Text c="dimmed" size="sm">
                    No data yet.
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Paper>

      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Paper withBorder p="md" radius="md">
          <Text fw={600} mb="sm">
            Slowest queries
          </Text>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Question</Table.Th>
                <Table.Th>Time</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(slowest.data ?? []).map((q, i) => (
                <Table.Tr key={q.query_execution_id ?? i}>
                  <Table.Td>
                    <Text size="sm" lineClamp={1}>
                      {q.question ?? '—'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {q.execution_time_ms != null ? `${Math.round(q.execution_time_ms)} ms` : '—'}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>

        <Paper withBorder p="md" radius="md">
          <Text fw={600} mb="sm">
            Most-queried tables
          </Text>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Table</Table.Th>
                <Table.Th>Queries</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(tables.data ?? []).map((t) => (
                <Table.Tr key={t.table}>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {t.table}
                    </Text>
                  </Table.Td>
                  <Table.Td>{t.query_count}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      </SimpleGrid>
    </Stack>
  );
}
