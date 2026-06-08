import { useState } from 'react';
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { IconEdit, IconLayoutDashboard, IconPlus, IconTrash } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { useDashboards, useDeleteDashboard } from '../hooks/useDashboards';
import type { Dashboard } from '../types/api';
import { DashboardFormModal } from '../components/dashboards/DashboardFormModal';

export function DashboardsPage() {
  const navigate = useNavigate();
  const { data: dashboards, isLoading } = useDashboards();
  const deleteMutation = useDeleteDashboard();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Dashboard | null>(null);

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Dashboards</Title>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
        >
          New Dashboard
        </Button>
      </Group>

      {isLoading && (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      )}

      {dashboards?.length === 0 && (
        <Alert color="blue">
          No dashboards yet. Create one, then add tiles from your saved queries.
        </Alert>
      )}

      {dashboards && dashboards.length > 0 && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          {dashboards.map((d) => (
            <Card
              key={d.id}
              withBorder
              padding="md"
              style={{ cursor: 'pointer' }}
              onClick={() => navigate(`/dashboards/${d.id}`)}
            >
              <Group justify="space-between" mb="xs" wrap="nowrap">
                <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                  <IconLayoutDashboard size={18} />
                  <Text fw={600} truncate>
                    {d.name}
                  </Text>
                </Group>
                <Group gap={4} wrap="nowrap" onClick={(e) => e.stopPropagation()}>
                  <Tooltip label="Edit">
                    <ActionIcon
                      variant="subtle"
                      onClick={() => {
                        setEditing(d);
                        setFormOpen(true);
                      }}
                    >
                      <IconEdit size={16} />
                    </ActionIcon>
                  </Tooltip>
                  <Tooltip label="Delete">
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      onClick={() => {
                        if (confirm(`Delete "${d.name}"?`)) deleteMutation.mutate(d.id);
                      }}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Tooltip>
                </Group>
              </Group>
              {d.description && (
                <Text size="sm" c="dimmed" lineClamp={2} mb="xs">
                  {d.description}
                </Text>
              )}
              <Group gap="xs">
                <Badge variant="light" color="gray">
                  {d.tiles.length} tiles
                </Badge>
                {d.is_public && <Badge variant="outline">shared</Badge>}
                {(d.filters?.length ?? 0) > 0 && (
                  <Badge variant="light" color="blue">
                    {d.filters!.length} filters
                  </Badge>
                )}
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      )}

      <DashboardFormModal
        opened={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        dashboard={editing}
        onCreated={(id) => navigate(`/dashboards/${id}`)}
      />
    </Stack>
  );
}
