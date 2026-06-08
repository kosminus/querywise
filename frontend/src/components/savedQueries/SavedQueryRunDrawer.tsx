import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Drawer,
  Group,
  Loader,
  Menu,
  MultiSelect,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconDownload, IconPlayerPlay, IconRefresh } from '@tabler/icons-react';
import {
  useCharts,
  useDeleteChart,
  useRunSavedQuery,
  useSaveChart,
} from '../../hooks/useSavedQueries';
import type { ChartType, SavedQuery, SavedQueryRunResult } from '../../types/api';
import { ChartView } from '../charts/ChartView';
import { ParamInputs } from '../common/ParamInputs';
import { downloadCsv, downloadJson } from '../../utils/exportResult';

const CHART_TYPES: ChartType[] = ['table', 'line', 'bar', 'area', 'pie', 'scatter'];

export function SavedQueryRunDrawer({
  opened,
  onClose,
  connectionId,
  savedQuery,
}: {
  opened: boolean;
  onClose: () => void;
  connectionId: string;
  savedQuery: SavedQuery;
}) {
  const params = savedQuery.params ?? [];
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [refresh, setRefresh] = useState(false);
  const [result, setResult] = useState<SavedQueryRunResult | null>(null);

  const runMutation = useRunSavedQuery(connectionId);

  // Seed param values from defaults whenever the target saved query changes.
  useEffect(() => {
    const seed: Record<string, unknown> = {};
    for (const p of params) seed[p.name] = p.default ?? '';
    setValues(seed);
    setResult(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedQuery.id]);

  const runNow = () => {
    runMutation.mutate(
      { id: savedQuery.id, params: values, refresh },
      {
        onSuccess: (data) => setResult(data),
        onError: (err) =>
          notifications.show({ title: 'Run failed', message: (err as Error).message, color: 'red' }),
      },
    );
  };

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="xl"
      title={<Title order={4}>{savedQuery.name}</Title>}
    >
      <Stack gap="md">
        {params.length > 0 && (
          <Paper withBorder p="md">
            <Text fw={500} mb="xs">
              Parameters
            </Text>
            <ParamInputs
              params={params}
              values={values}
              onChange={(name, value) => setValues((s) => ({ ...s, [name]: value }))}
            />
          </Paper>
        )}

        <Group>
          <Button
            leftSection={<IconPlayerPlay size={16} />}
            onClick={runNow}
            loading={runMutation.isPending}
          >
            Run
          </Button>
          <Switch
            label="Refresh (bypass cache)"
            checked={refresh}
            onChange={(e) => setRefresh(e.currentTarget.checked)}
            thumbIcon={<IconRefresh size={10} />}
          />
        </Group>

        {runMutation.isPending && (
          <Group justify="center" py="lg">
            <Loader />
          </Group>
        )}

        {result && <RunResult result={result} baseName={savedQuery.name} />}

        {result && result.columns.length > 0 && (
          <ChartPanel
            connectionId={connectionId}
            savedQueryId={savedQuery.id}
            columns={result.columns}
            rows={result.rows}
          />
        )}
      </Stack>
    </Drawer>
  );
}

function RunResult({ result, baseName }: { result: SavedQueryRunResult; baseName: string }) {
  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="xs">
        <Group gap="xs">
          <Badge variant="light" color="gray">
            {result.row_count} rows
          </Badge>
          <Badge variant="light" color={result.cached ? 'orange' : 'green'}>
            {result.cached ? 'cached' : 'fresh'}
          </Badge>
          <Text size="xs" c="dimmed">
            {new Date(result.taken_at).toLocaleString()}
          </Text>
        </Group>
        <Menu position="bottom-end" withinPortal>
          <Menu.Target>
            <Button
              variant="default"
              size="xs"
              leftSection={<IconDownload size={14} />}
              disabled={result.rows.length === 0}
            >
              Export
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item onClick={() => downloadCsv(result.columns, result.rows, baseName)}>
              CSV
            </Menu.Item>
            <Menu.Item onClick={() => downloadJson(result.columns, result.rows, baseName)}>
              JSON
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>
      {result.rows.length > 0 ? (
        <Table.ScrollContainer minWidth={400}>
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                {result.columns.map((c) => (
                  <Table.Th key={c}>{c}</Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {result.rows.slice(0, 200).map((row, i) => (
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
        </Table.ScrollContainer>
      ) : (
        <Text c="dimmed">No rows returned.</Text>
      )}
    </Paper>
  );
}

function ChartPanel({
  connectionId,
  savedQueryId,
  columns,
  rows,
}: {
  connectionId: string;
  savedQueryId: string;
  columns: string[];
  rows: unknown[][];
}) {
  const { data: charts } = useCharts(connectionId, savedQueryId);
  const saveChart = useSaveChart(connectionId, savedQueryId);
  const deleteChart = useDeleteChart(connectionId, savedQueryId);

  const [chartId, setChartId] = useState<string | undefined>(undefined);
  const [chartType, setChartType] = useState<ChartType>('bar');
  const [xAxis, setXAxis] = useState<string | null>(columns[0] ?? null);
  const [yAxis, setYAxis] = useState<string[]>(columns.slice(1, 2));

  const colOptions = useMemo(() => columns.map((c) => ({ value: c, label: c })), [columns]);

  const loadChart = (id: string | null) => {
    setChartId(id ?? undefined);
    const c = charts?.find((ch) => ch.id === id);
    if (c) {
      setChartType(c.chart_type);
      setXAxis((c.config?.x_axis as string) ?? columns[0] ?? null);
      setYAxis((c.config?.y_axis as string[]) ?? []);
    }
  };

  const handleSave = () => {
    saveChart.mutate(
      {
        chartId,
        name: chartId ? (charts?.find((c) => c.id === chartId)?.name ?? 'Chart') : 'Chart',
        chart_type: chartType,
        config: { x_axis: xAxis ?? undefined, y_axis: yAxis },
      },
      {
        onSuccess: () =>
          notifications.show({ message: 'Chart saved', color: 'green' }),
        onError: (err) =>
          notifications.show({ message: (err as Error).message, color: 'red' }),
      },
    );
  };

  return (
    <Paper withBorder p="md">
      <Text fw={500} mb="xs">
        Chart
      </Text>
      <Group align="flex-end" mb="md">
        {charts && charts.length > 0 && (
          <Select
            label="Saved chart"
            placeholder="New chart"
            clearable
            w={160}
            data={charts.map((c) => ({ value: c.id, label: c.name }))}
            value={chartId ?? null}
            onChange={loadChart}
          />
        )}
        <Select
          label="Type"
          w={130}
          data={CHART_TYPES}
          value={chartType}
          onChange={(v) => v && setChartType(v as ChartType)}
        />
        <Select
          label="X axis"
          w={160}
          data={colOptions}
          value={xAxis}
          onChange={setXAxis}
        />
        <MultiSelect
          label="Y series"
          w={220}
          data={colOptions}
          value={yAxis}
          onChange={setYAxis}
        />
        <Button variant="light" onClick={handleSave} loading={saveChart.isPending}>
          Save chart
        </Button>
        {chartId && (
          <Button
            variant="subtle"
            color="red"
            onClick={() =>
              deleteChart.mutate(chartId, {
                onSuccess: () => {
                  setChartId(undefined);
                  notifications.show({ message: 'Chart deleted', color: 'gray' });
                },
              })
            }
          >
            Delete
          </Button>
        )}
      </Group>
      {chartType === 'table' ? (
        <Alert color="gray">Table view — see the result table above.</Alert>
      ) : (
        <ChartView
          columns={columns}
          rows={rows}
          chartType={chartType}
          xAxis={xAxis ?? undefined}
          yAxis={yAxis}
        />
      )}
    </Paper>
  );
}
