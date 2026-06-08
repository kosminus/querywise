import { useState } from 'react';
import {
  Stack,
  Title,
  Group,
  Text,
  Badge,
  Button,
  Modal,
  TextInput,
  Select,
  Switch,
  Table,
  ActionIcon,
  Tooltip,
  Alert,
  Loader,
  NumberInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useQuery } from '@tanstack/react-query';
import { IconPlayerPlay, IconPencil, IconTrash, IconPlus } from '@tabler/icons-react';
import { useConnections } from '../hooks/useConnections';
import { useDashboards } from '../hooks/useDashboards';
import { savedQueriesApi } from '../api/savedQueriesApi';
import {
  useSchedules,
  useCreateSchedule,
  useUpdateSchedule,
  useDeleteSchedule,
  useRunSchedule,
} from '../hooks/useSchedules';
import type { Schedule } from '../types/api';

const STATUS_COLORS: Record<string, string> = {
  success: 'green',
  error: 'red',
  skipped: 'gray',
  pending: 'yellow',
};

interface FormValues {
  name: string;
  target_type: 'saved_query' | 'dashboard';
  connection_id: string;
  target_id: string;
  cron: string;
  channel: 'email' | 'slack' | 'log';
  recipients: string;
  enabled: boolean;
  threshold_metric: string;
  threshold_op: string;
  threshold_value: number | '';
  only_on_threshold: boolean;
}

export function SchedulesPage() {
  const { data: schedules, isLoading } = useSchedules();
  const del = useDeleteSchedule();
  const run = useRunSchedule();
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [open, setOpen] = useState(false);

  function openCreate() {
    setEditing(null);
    setOpen(true);
  }
  function openEdit(s: Schedule) {
    setEditing(s);
    setOpen(true);
  }

  if (isLoading)
    return (
      <Group justify="center" py="xl">
        <Loader />
      </Group>
    );

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Scheduled Reports</Title>
        <Button leftSection={<IconPlus size={16} />} onClick={openCreate}>
          New schedule
        </Button>
      </Group>

      {(!schedules || schedules.length === 0) && (
        <Alert color="blue">No schedules yet. Create one to deliver a report on a cron.</Alert>
      )}

      {schedules && schedules.length > 0 && (
        <Table highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Cron</Table.Th>
              <Table.Th>Channel</Table.Th>
              <Table.Th>Next run</Table.Th>
              <Table.Th>Last</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {schedules.map((s) => (
              <Table.Tr key={s.id}>
                <Table.Td>
                  <Group gap="xs">
                    <Text size="sm" fw={500}>
                      {s.name}
                    </Text>
                    {!s.enabled && (
                      <Badge size="xs" color="gray" variant="light">
                        disabled
                      </Badge>
                    )}
                  </Group>
                  <Text size="xs" c="dimmed">
                    {s.target_type}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs" ff="monospace">
                    {s.cron}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Badge variant="light" size="sm">
                    {s.channel}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">
                    {s.next_run_at ? new Date(s.next_run_at).toLocaleString() : '—'}
                  </Text>
                </Table.Td>
                <Table.Td>
                  {s.last_status ? (
                    <Tooltip
                      label={s.last_error || s.last_run_at || ''}
                      disabled={!s.last_error && !s.last_run_at}
                    >
                      <Badge size="sm" color={STATUS_COLORS[s.last_status] ?? 'gray'} variant="light">
                        {s.last_status}
                      </Badge>
                    </Tooltip>
                  ) : (
                    <Text size="xs" c="dimmed">
                      never
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    <Tooltip label="Run now">
                      <ActionIcon
                        variant="subtle"
                        color="green"
                        loading={run.isPending && run.variables === s.id}
                        onClick={() => run.mutate(s.id)}
                      >
                        <IconPlayerPlay size={16} />
                      </ActionIcon>
                    </Tooltip>
                    <ActionIcon variant="subtle" onClick={() => openEdit(s)}>
                      <IconPencil size={16} />
                    </ActionIcon>
                    <ActionIcon variant="subtle" color="red" onClick={() => del.mutate(s.id)}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {open && (
        <ScheduleFormModal schedule={editing} onClose={() => setOpen(false)} />
      )}
    </Stack>
  );
}

function ScheduleFormModal({
  schedule,
  onClose,
}: {
  schedule: Schedule | null;
  onClose: () => void;
}) {
  const create = useCreateSchedule();
  const update = useUpdateSchedule();
  const { data: connections } = useConnections();
  const { data: dashboards } = useDashboards();

  const form = useForm<FormValues>({
    initialValues: {
      name: schedule?.name ?? '',
      target_type: schedule?.target_type ?? 'saved_query',
      connection_id: '',
      target_id: schedule?.target_id ?? '',
      cron: schedule?.cron ?? '0 9 * * *',
      channel: schedule?.channel ?? 'email',
      recipients: (schedule?.recipients ?? []).join(', '),
      enabled: schedule?.enabled ?? true,
      threshold_metric: schedule?.threshold?.metric ?? '',
      threshold_op: schedule?.threshold?.op ?? '>',
      threshold_value: schedule?.threshold?.value ?? '',
      only_on_threshold: schedule?.only_on_threshold ?? false,
    },
  });

  const { data: savedQueries } = useQuery({
    queryKey: ['saved-queries', form.values.connection_id],
    queryFn: () => savedQueriesApi.list(form.values.connection_id),
    enabled: form.values.target_type === 'saved_query' && !!form.values.connection_id,
  });

  function submit(v: FormValues) {
    const payload: Partial<Schedule> = {
      name: v.name,
      target_type: v.target_type,
      target_id: v.target_id,
      cron: v.cron,
      channel: v.channel,
      recipients: v.recipients
        .split(',')
        .map((r) => r.trim())
        .filter(Boolean),
      enabled: v.enabled,
      only_on_threshold: v.only_on_threshold,
      threshold:
        v.threshold_metric && v.threshold_value !== ''
          ? { metric: v.threshold_metric, op: v.threshold_op, value: Number(v.threshold_value) }
          : null,
    };
    const done = () => onClose();
    if (schedule) update.mutate({ id: schedule.id, data: payload }, { onSuccess: done });
    else create.mutate(payload, { onSuccess: done });
  }

  return (
    <Modal opened onClose={onClose} title={schedule ? 'Edit schedule' : 'New schedule'} size="lg">
      <form onSubmit={form.onSubmit(submit)}>
        <Stack gap="sm">
          <TextInput label="Name" required {...form.getInputProps('name')} />
          <Group grow>
            <Select
              label="Target type"
              data={[
                { value: 'saved_query', label: 'Saved query' },
                { value: 'dashboard', label: 'Dashboard' },
              ]}
              {...form.getInputProps('target_type')}
            />
            {form.values.target_type === 'saved_query' ? (
              <Select
                label="Connection"
                data={(connections ?? []).map((c) => ({ value: c.id, label: c.name }))}
                {...form.getInputProps('connection_id')}
              />
            ) : (
              <Select
                label="Dashboard"
                data={(dashboards ?? []).map((d) => ({ value: d.id, label: d.name }))}
                {...form.getInputProps('target_id')}
              />
            )}
          </Group>

          {form.values.target_type === 'saved_query' && (
            <Select
              label="Saved query"
              data={(savedQueries ?? []).map((q) => ({ value: q.id, label: q.name }))}
              disabled={!form.values.connection_id}
              {...form.getInputProps('target_id')}
            />
          )}

          <Group grow>
            <TextInput
              label="Cron (UTC)"
              placeholder="0 9 * * *"
              description="min hour day month weekday"
              required
              {...form.getInputProps('cron')}
            />
            <Select
              label="Channel"
              data={['email', 'slack', 'log']}
              {...form.getInputProps('channel')}
            />
          </Group>

          {form.values.channel === 'email' && (
            <TextInput
              label="Recipients"
              placeholder="alice@co.com, bob@co.com"
              description="Comma-separated email addresses"
              {...form.getInputProps('recipients')}
            />
          )}

          <Group grow align="flex-end">
            <TextInput
              label="Threshold metric"
              placeholder="row_count or column name"
              {...form.getInputProps('threshold_metric')}
            />
            <Select
              label="Op"
              data={['>', '>=', '<', '<=', '==', '!=']}
              {...form.getInputProps('threshold_op')}
            />
            <NumberInput label="Value" {...form.getInputProps('threshold_value')} />
          </Group>

          <Switch
            label="Only deliver when threshold is met"
            {...form.getInputProps('only_on_threshold', { type: 'checkbox' })}
          />
          <Switch
            label="Enabled"
            {...form.getInputProps('enabled', { type: 'checkbox' })}
          />

          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending || update.isPending}>
              {schedule ? 'Save' : 'Create'}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
