import { useState } from 'react';
import { Button, Group, Modal, Select, Stack, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useConnections } from '../../hooks/useConnections';
import { useSavedQueries, useCharts } from '../../hooks/useSavedQueries';
import { useAddTile } from '../../hooks/useDashboards';

export function AddTileModal({
  opened,
  onClose,
  dashboardId,
}: {
  opened: boolean;
  onClose: () => void;
  dashboardId: string;
}) {
  const { data: connections } = useConnections();
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [savedQueryId, setSavedQueryId] = useState<string | null>(null);
  const [chartId, setChartId] = useState<string | null>(null);
  const [title, setTitle] = useState('');

  const { data: savedQueries } = useSavedQueries(connectionId ?? undefined);
  const { data: charts } = useCharts(connectionId ?? undefined, savedQueryId ?? undefined);
  const addTile = useAddTile(dashboardId);

  const reset = () => {
    setSavedQueryId(null);
    setChartId(null);
    setTitle('');
  };

  const handleAdd = () => {
    if (!savedQueryId) return;
    const chosen = savedQueries?.find((s) => s.id === savedQueryId);
    addTile.mutate(
      {
        saved_query_id: savedQueryId,
        chart_id: chartId,
        title: title || chosen?.name || null,
      },
      {
        onSuccess: () => {
          notifications.show({ message: 'Tile added', color: 'green' });
          reset();
          onClose();
        },
        onError: (err) =>
          notifications.show({ message: (err as Error).message, color: 'red' }),
      },
    );
  };

  return (
    <Modal opened={opened} onClose={onClose} title="Add tile" size="lg">
      <Stack gap="sm">
        <Select
          label="Connection"
          data={connections?.map((c) => ({ value: c.id, label: c.name })) ?? []}
          value={connectionId}
          onChange={(v) => {
            setConnectionId(v);
            setSavedQueryId(null);
            setChartId(null);
          }}
        />
        <Select
          label="Saved query"
          placeholder={connectionId ? 'Pick a saved query' : 'Select a connection first'}
          disabled={!connectionId}
          data={savedQueries?.map((s) => ({ value: s.id, label: s.name })) ?? []}
          value={savedQueryId}
          onChange={(v) => {
            setSavedQueryId(v);
            setChartId(null);
          }}
        />
        <Select
          label="Chart (optional — leave empty for a table)"
          placeholder="Table view"
          clearable
          disabled={!savedQueryId || !charts || charts.length === 0}
          data={charts?.map((c) => ({ value: c.id, label: `${c.name} (${c.chart_type})` })) ?? []}
          value={chartId}
          onChange={setChartId}
        />
        <TextInput
          label="Tile title (optional)"
          placeholder="Defaults to the saved-query name"
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
        />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleAdd} disabled={!savedQueryId} loading={addTile.isPending}>
            Add tile
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
