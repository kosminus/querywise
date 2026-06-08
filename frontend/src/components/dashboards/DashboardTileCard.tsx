import { ActionIcon, Badge, Group, Loader, Paper, Table, Text, Tooltip } from '@mantine/core';
import { IconGripVertical, IconRefresh, IconTrash } from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { dashboardsApi } from '../../api/dashboardsApi';
import type { DashboardTile, TileRunResult } from '../../types/api';
import { ChartView } from '../charts/ChartView';

export function DashboardTileCard({
  dashboardId,
  tile,
  filterValues,
  editable,
  onDelete,
}: {
  dashboardId: string;
  tile: DashboardTile;
  filterValues: Record<string, unknown>;
  editable: boolean;
  onDelete: () => void;
}) {
  const query = useQuery({
    queryKey: ['tileRun', dashboardId, tile.id, filterValues],
    queryFn: () => dashboardsApi.runTile(dashboardId, tile.id, filterValues),
    refetchInterval: tile.refresh_interval ? tile.refresh_interval * 1000 : false,
  });

  const result = query.data;

  return (
    <Paper withBorder h="100%" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <Group
        className="tile-drag-handle"
        justify="space-between"
        px="sm"
        py={6}
        style={{ cursor: editable ? 'move' : 'default', borderBottom: '1px solid var(--mantine-color-gray-3)' }}
      >
        <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
          {editable && <IconGripVertical size={14} style={{ color: 'var(--mantine-color-dimmed)' }} />}
          <Text fw={600} size="sm" truncate>
            {tile.title || 'Untitled tile'}
          </Text>
          {result && (
            <Badge size="xs" variant="light" color={result.cached ? 'orange' : 'green'}>
              {result.cached ? 'cached' : 'fresh'}
            </Badge>
          )}
        </Group>
        <Group gap={2} wrap="nowrap">
          <Tooltip label="Refresh">
            <ActionIcon variant="subtle" size="sm" onClick={() => query.refetch()}>
              <IconRefresh size={14} />
            </ActionIcon>
          </Tooltip>
          {editable && (
            <Tooltip label="Remove tile">
              <ActionIcon variant="subtle" size="sm" color="red" onClick={onDelete}>
                <IconTrash size={14} />
              </ActionIcon>
            </Tooltip>
          )}
        </Group>
      </Group>

      <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
        {query.isLoading && (
          <Group justify="center" py="lg">
            <Loader size="sm" />
          </Group>
        )}
        {query.isError && (
          <Text c="red" size="sm">
            {(query.error as Error).message}
          </Text>
        )}
        {result && <TileBody result={result} />}
      </div>
    </Paper>
  );
}

function TileBody({ result }: { result: TileRunResult }) {
  if (result.rows.length === 0) {
    return (
      <Text c="dimmed" size="sm">
        No rows.
      </Text>
    );
  }
  if (result.chart_type && result.chart_type !== 'table') {
    return (
      <ChartView
        columns={result.columns}
        rows={result.rows}
        chartType={result.chart_type}
        xAxis={result.chart_config?.x_axis as string | undefined}
        yAxis={result.chart_config?.y_axis as string[] | undefined}
        height={220}
      />
    );
  }
  return (
    <Table striped highlightOnHover withTableBorder fz="xs">
      <Table.Thead>
        <Table.Tr>
          {result.columns.map((c) => (
            <Table.Th key={c}>{c}</Table.Th>
          ))}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {result.rows.slice(0, 100).map((row, i) => (
          <Table.Tr key={i}>
            {row.map((cell, j) => (
              <Table.Td key={j}>{cell === null ? '—' : String(cell)}</Table.Td>
            ))}
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
