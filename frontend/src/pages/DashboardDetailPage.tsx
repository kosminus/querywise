import { useState } from 'react';
import {
  ActionIcon,
  Alert,
  Button,
  Group,
  Loader,
  Stack,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { IconArrowLeft, IconEdit, IconPlus } from '@tabler/icons-react';
import { useNavigate, useParams } from 'react-router-dom';
import { useDashboard, useDeleteTile } from '../hooks/useDashboards';
import { useAuth } from '../context/auth';
import type { Dashboard } from '../types/api';
import { DashboardFiltersBar } from '../components/dashboards/DashboardFiltersBar';
import { DashboardGrid } from '../components/dashboards/DashboardGrid';
import { AddTileModal } from '../components/dashboards/AddTileModal';
import { DashboardFormModal } from '../components/dashboards/DashboardFormModal';

export function DashboardDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { role } = useAuth();
  const editable = role === 'admin' || role === 'editor';

  const { data: dashboard, isLoading } = useDashboard(id);
  const deleteTile = useDeleteTile(id ?? '');

  const [addOpen, setAddOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  if (isLoading) {
    return (
      <Group justify="center" py="xl">
        <Loader />
      </Group>
    );
  }
  if (!dashboard || !id) {
    return <Alert color="red">Dashboard not found.</Alert>;
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Group gap="xs">
          <Tooltip label="Back to dashboards">
            <ActionIcon variant="subtle" onClick={() => navigate('/dashboards')}>
              <IconArrowLeft size={18} />
            </ActionIcon>
          </Tooltip>
          <Title order={2}>{dashboard.name}</Title>
        </Group>
        {editable && (
          <Group gap="xs">
            <Button variant="default" leftSection={<IconEdit size={16} />} onClick={() => setEditOpen(true)}>
              Edit
            </Button>
            <Button leftSection={<IconPlus size={16} />} onClick={() => setAddOpen(true)}>
              Add tile
            </Button>
          </Group>
        )}
      </Group>

      {dashboard.description && <Text c="dimmed">{dashboard.description}</Text>}

      {/* Keyed by dashboard id so filter state re-initializes from defaults per dashboard. */}
      <DashboardCanvas
        key={dashboard.id}
        dashboard={dashboard}
        editable={editable}
        onDeleteTile={(tileId) => {
          if (confirm('Remove this tile?')) deleteTile.mutate(tileId);
        }}
      />

      <AddTileModal opened={addOpen} onClose={() => setAddOpen(false)} dashboardId={id} />
      <DashboardFormModal opened={editOpen} onClose={() => setEditOpen(false)} dashboard={dashboard} />
    </Stack>
  );
}

function DashboardCanvas({
  dashboard,
  editable,
  onDeleteTile,
}: {
  dashboard: Dashboard;
  editable: boolean;
  onDeleteTile: (tileId: string) => void;
}) {
  const filters = dashboard.filters ?? [];
  const seed = () => {
    const s: Record<string, unknown> = {};
    for (const f of filters) s[f.name] = f.default ?? '';
    return s;
  };
  const [draft, setDraft] = useState<Record<string, unknown>>(seed);
  const [applied, setApplied] = useState<Record<string, unknown>>(seed);

  return (
    <>
      <DashboardFiltersBar
        filters={filters}
        values={draft}
        onChange={(name, value) => setDraft((s) => ({ ...s, [name]: value }))}
        onApply={() => setApplied({ ...draft })}
      />

      {dashboard.tiles.length === 0 ? (
        <Alert color="blue" mt="md">
          No tiles yet.{editable ? ' Click “Add tile” to chart a saved query here.' : ''}
        </Alert>
      ) : (
        <DashboardGrid
          dashboard={dashboard}
          filterValues={applied}
          editable={editable}
          onDeleteTile={onDeleteTile}
        />
      )}
    </>
  );
}
