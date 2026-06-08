import { useState, useEffect } from 'react';
import {
  Stack,
  Title,
  Button,
  Group,
  Text,
  Table,
  Modal,
  TextInput,
  Textarea,
  Select,
  ActionIcon,
  Tooltip,
  Alert,
  Loader,
  Badge,
  Code,
  TagsInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconPlus, IconTrash, IconEdit, IconHistory } from '@tabler/icons-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { metricsApi } from '../api/glossaryApi';
import { useConnections } from '../hooks/useConnections';
import type { MetricDefinition } from '../types/api';
import { CertificationBadge } from '../components/common/CertificationBadge';
import { StatusActions } from '../components/common/StatusActions';
import { VersionHistory } from '../components/common/VersionHistory';

export function MetricsPage() {
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editingMetric, setEditingMetric] = useState<MetricDefinition | null>(
    null
  );
  const [historyFor, setHistoryFor] = useState<MetricDefinition | null>(null);

  const { data: connections } = useConnections();
  const qc = useQueryClient();

  const connOptions =
    connections?.map((c) => ({ value: c.id, label: c.name })) ?? [];
  if (!connectionId && connOptions.length > 0) {
    setConnectionId(connOptions[0].value);
  }

  const { data: metrics, isLoading } = useQuery({
    queryKey: ['metrics', connectionId],
    queryFn: () => metricsApi.list(connectionId!),
    enabled: !!connectionId,
  });

  const deleteMutation = useMutation({
    mutationFn: ({ connId, metricId }: { connId: string; metricId: string }) =>
      metricsApi.delete(connId, metricId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['metrics', connectionId] }),
  });

  const transitionMutation = useMutation({
    mutationFn: ({ metricId, status, reason }: { metricId: string; status: string; reason?: string }) =>
      metricsApi.transitionStatus(connectionId!, metricId, status, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metrics', connectionId] });
      notifications.show({ message: 'Status updated', color: 'green' });
    },
    onError: (e: unknown) =>
      notifications.show({
        message: e instanceof Error ? e.message : 'Transition failed',
        color: 'red',
      }),
  });

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Metric Definitions</Title>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={() => setAddOpen(true)}
          disabled={!connectionId}
        >
          Add Metric
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

      {metrics?.length === 0 && (
        <Alert color="blue">
          No metrics defined yet. Define named metrics to standardize
          calculations.
        </Alert>
      )}

      {metrics && metrics.length > 0 && (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Description</Table.Th>
              <Table.Th>SQL Expression</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th w={130}>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {metrics.map((m: MetricDefinition) => (
              <Table.Tr key={m.id}>
                <Table.Td>
                  <Text fw={500}>{m.display_name}</Text>
                  <Text size="xs" c="dimmed">
                    {m.metric_name}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" lineClamp={2}>
                    {m.description}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Code>{m.sql_expression}</Code>
                </Table.Td>
                <Table.Td>
                  <Group gap={6}>
                    <CertificationBadge status={m.status} />
                    <Text size="xs" c="dimmed">
                      v{m.version}
                    </Text>
                    {m.aggregation_type && (
                      <Badge size="xs" variant="outline">
                        {m.aggregation_type}
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    <Tooltip label="Edit">
                      <ActionIcon
                        variant="subtle"
                        size="sm"
                        onClick={() => setEditingMetric(m)}
                      >
                        <IconEdit size={14} />
                      </ActionIcon>
                    </Tooltip>
                    <Tooltip label="Version history">
                      <ActionIcon variant="subtle" size="sm" onClick={() => setHistoryFor(m)}>
                        <IconHistory size={14} />
                      </ActionIcon>
                    </Tooltip>
                    <StatusActions
                      status={m.status}
                      onTransition={(status, reason) =>
                        transitionMutation.mutate({ metricId: m.id, status, reason })
                      }
                    />
                    <Tooltip label="Delete">
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        size="sm"
                        onClick={() => {
                          if (confirm(`Delete "${m.display_name}"?`))
                            deleteMutation.mutate({
                              connId: connectionId!,
                              metricId: m.id,
                            });
                        }}
                      >
                        <IconTrash size={14} />
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
        <MetricFormModal
          opened={addOpen || !!editingMetric}
          onClose={() => {
            setAddOpen(false);
            setEditingMetric(null);
          }}
          connectionId={connectionId}
          metric={editingMetric}
        />
      )}

      {connectionId && historyFor && (
        <VersionHistory
          opened={!!historyFor}
          onClose={() => setHistoryFor(null)}
          title={historyFor.display_name}
          queryKey={['metricVersions', connectionId, historyFor.id]}
          fetchVersions={() => metricsApi.versions(connectionId, historyFor.id)}
        />
      )}
    </Stack>
  );
}

function MetricFormModal({
  opened,
  onClose,
  connectionId,
  metric,
}: {
  opened: boolean;
  onClose: () => void;
  connectionId: string;
  metric: MetricDefinition | null;
}) {
  const qc = useQueryClient();
  const isEdit = !!metric;

  const form = useForm({
    initialValues: {
      metric_name: '',
      display_name: '',
      description: '',
      sql_expression: '',
      aggregation_type: '',
      related_tables: [] as string[],
      dimensions: [] as string[],
    },
  });

  useEffect(() => {
    if (metric) {
      form.setValues({
        metric_name: metric.metric_name,
        display_name: metric.display_name,
        description: metric.description ?? '',
        sql_expression: metric.sql_expression ?? '',
        aggregation_type: metric.aggregation_type ?? '',
        related_tables: metric.related_tables ?? [],
        dimensions: metric.dimensions ?? [],
      });
    } else {
      form.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric]);

  const mutation = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      isEdit
        ? metricsApi.update(connectionId, metric!.id, values)
        : metricsApi.create(connectionId, values),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['metrics', connectionId] });
      notifications.show({
        title: isEdit ? 'Metric updated' : 'Metric created',
        message: `"${form.values.display_name}" saved`,
        color: 'green',
      });
      form.reset();
      onClose();
    },
  });

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={isEdit ? 'Edit Metric' : 'Add Metric'}
      size="lg"
    >
      <form onSubmit={form.onSubmit((v) => mutation.mutate(v))}>
        <Stack gap="sm">
          <Group grow>
            <TextInput
              label="Metric key"
              placeholder="e.g. total_ecl"
              required
              {...form.getInputProps('metric_name')}
            />
            <TextInput
              label="Display name"
              placeholder="e.g. Total ECL"
              required
              {...form.getInputProps('display_name')}
            />
          </Group>
          <Textarea
            label="Description"
            autosize
            minRows={2}
            {...form.getInputProps('description')}
          />
          <Textarea
            label="SQL Expression"
            required
            placeholder="e.g. SUM(ecl_provisions.ecl_lifetime)"
            autosize
            minRows={2}
            {...form.getInputProps('sql_expression')}
          />
          <Select
            label="Aggregation type"
            data={['SUM', 'COUNT', 'AVG', 'MIN', 'MAX', 'COUNT_DISTINCT']}
            clearable
            {...form.getInputProps('aggregation_type')}
          />
          <TagsInput
            label="Related Tables"
            placeholder="Type table name and press Enter"
            {...form.getInputProps('related_tables')}
          />
          <TagsInput
            label="Dimensions"
            placeholder="Type dimension column and press Enter"
            {...form.getInputProps('dimensions')}
          />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {isEdit ? 'Update' : 'Create'}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
