import { useState } from 'react';
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import {
  IconCopy,
  IconEdit,
  IconPlayerPlay,
  IconPlus,
  IconTrash,
} from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { useConnections } from '../hooks/useConnections';
import {
  useCloneSavedQuery,
  useDeleteSavedQuery,
  useSavedQueries,
} from '../hooks/useSavedQueries';
import type { SavedQuery } from '../types/api';
import { SavedQueryFormModal } from '../components/savedQueries/SavedQueryFormModal';
import { SavedQueryRunDrawer } from '../components/savedQueries/SavedQueryRunDrawer';

const STATUS_COLOR: Record<string, string> = {
  certified: 'green',
  draft: 'gray',
  deprecated: 'red',
};

export function SavedQueriesPage() {
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<SavedQuery | null>(null);
  const [running, setRunning] = useState<SavedQuery | null>(null);

  const { data: connections } = useConnections();
  const connOptions = connections?.map((c) => ({ value: c.id, label: c.name })) ?? [];
  if (!connectionId && connOptions.length > 0) {
    setConnectionId(connOptions[0].value);
  }

  const { data: savedQueries, isLoading } = useSavedQueries(connectionId ?? undefined);
  const deleteMutation = useDeleteSavedQuery(connectionId ?? '');
  const cloneMutation = useCloneSavedQuery(connectionId ?? '');

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Saved Queries</Title>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
          disabled={!connectionId}
        >
          New Saved Query
        </Button>
      </Group>

      <Select
        label="Connection"
        data={connOptions}
        value={connectionId}
        onChange={setConnectionId}
        w={300}
      />

      {isLoading && (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      )}

      {savedQueries?.length === 0 && (
        <Alert color="blue">
          No saved queries yet. Run a question on the Query page and click “Save query”, or create
          one here.
        </Alert>
      )}

      {savedQueries && savedQueries.length > 0 && (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th w={90}>Version</Table.Th>
              <Table.Th>Updated</Table.Th>
              <Table.Th w={160}>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {savedQueries.map((sq) => (
              <Table.Tr key={sq.id}>
                <Table.Td>
                  <Text fw={500}>{sq.name}</Text>
                  {sq.description && (
                    <Text size="xs" c="dimmed" lineClamp={1}>
                      {sq.description}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Group gap={6}>
                    <Badge size="sm" variant="light" color={STATUS_COLOR[sq.status] ?? 'gray'}>
                      {sq.status}
                    </Badge>
                    {sq.is_public && (
                      <Badge size="sm" variant="outline">
                        shared
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td>v{sq.version}</Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {new Date(sq.updated_at).toLocaleString()}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    <Tooltip label="Run">
                      <ActionIcon variant="subtle" color="green" onClick={() => setRunning(sq)}>
                        <IconPlayerPlay size={16} />
                      </ActionIcon>
                    </Tooltip>
                    <Tooltip label="Edit">
                      <ActionIcon
                        variant="subtle"
                        onClick={() => {
                          setEditing(sq);
                          setFormOpen(true);
                        }}
                      >
                        <IconEdit size={16} />
                      </ActionIcon>
                    </Tooltip>
                    <Tooltip label="Clone">
                      <ActionIcon
                        variant="subtle"
                        onClick={() =>
                          cloneMutation.mutate(sq.id, {
                            onSuccess: () =>
                              notifications.show({ message: 'Cloned', color: 'green' }),
                          })
                        }
                      >
                        <IconCopy size={16} />
                      </ActionIcon>
                    </Tooltip>
                    <Tooltip label="Delete">
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        onClick={() => {
                          if (confirm(`Delete "${sq.name}"?`)) deleteMutation.mutate(sq.id);
                        }}
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Tooltip>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {connectionId && (
        <SavedQueryFormModal
          opened={formOpen}
          onClose={() => {
            setFormOpen(false);
            setEditing(null);
          }}
          connectionId={connectionId}
          savedQuery={editing}
        />
      )}

      {connectionId && running && (
        <SavedQueryRunDrawer
          opened={!!running}
          onClose={() => setRunning(null)}
          connectionId={connectionId}
          savedQuery={running}
        />
      )}
    </Stack>
  );
}
