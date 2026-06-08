import { useEffect } from 'react';
import {
  ActionIcon,
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import { useCreateDashboard, useUpdateDashboard } from '../../hooks/useDashboards';
import type { Dashboard, DashboardFilter, ParamType } from '../../types/api';

const PARAM_TYPES: ParamType[] = ['string', 'number', 'date', 'boolean'];

interface FormValues {
  name: string;
  description: string;
  is_public: boolean;
  filters: DashboardFilter[];
}

export function DashboardFormModal({
  opened,
  onClose,
  dashboard,
  onCreated,
}: {
  opened: boolean;
  onClose: () => void;
  dashboard: Dashboard | null;
  onCreated?: (id: string) => void;
}) {
  const isEdit = !!dashboard;
  const createMutation = useCreateDashboard();
  const updateMutation = useUpdateDashboard(dashboard?.id ?? '');

  const form = useForm<FormValues>({
    initialValues: { name: '', description: '', is_public: false, filters: [] },
  });

  useEffect(() => {
    if (dashboard) {
      form.setValues({
        name: dashboard.name,
        description: dashboard.description ?? '',
        is_public: dashboard.is_public,
        filters: dashboard.filters ?? [],
      });
    } else {
      form.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dashboard, opened]);

  const handleSubmit = (values: FormValues) => {
    const payload = {
      name: values.name,
      description: values.description || null,
      is_public: values.is_public,
      filters: values.filters,
    };
    const done = (d?: Dashboard) => {
      notifications.show({
        title: isEdit ? 'Dashboard updated' : 'Dashboard created',
        message: `"${values.name}" saved`,
        color: 'green',
      });
      form.reset();
      onClose();
      if (d && onCreated) onCreated(d.id);
    };
    const onError = (err: unknown) =>
      notifications.show({ title: 'Error', message: (err as Error).message, color: 'red' });

    if (isEdit) {
      updateMutation.mutate(payload, { onSuccess: () => done(), onError });
    } else {
      createMutation.mutate(payload, { onSuccess: (d) => done(d), onError });
    }
  };

  const addFilter = () =>
    form.setFieldValue('filters', [
      ...form.values.filters,
      { name: '', type: 'string', label: '', default: '' },
    ]);
  const removeFilter = (i: number) =>
    form.setFieldValue(
      'filters',
      form.values.filters.filter((_, idx) => idx !== i),
    );

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={isEdit ? 'Edit Dashboard' : 'New Dashboard'}
      size="xl"
    >
      <form onSubmit={form.onSubmit(handleSubmit)}>
        <Stack gap="sm">
          <TextInput label="Name" required {...form.getInputProps('name')} />
          <Textarea label="Description" autosize minRows={1} {...form.getInputProps('description')} />
          <Switch
            label="Shared with workspace"
            {...form.getInputProps('is_public', { type: 'checkbox' })}
          />

          <Group justify="space-between" align="center">
            <Text fw={500} size="sm">
              Filters
            </Text>
            <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={addFilter}>
              Add filter
            </Button>
          </Group>
          <Text size="xs" c="dimmed">
            A filter's value flows into any tile whose saved-query SQL uses {`{{name}}`}.
          </Text>
          {form.values.filters.map((_, i) => (
            <Group key={i} align="flex-end" gap="xs" wrap="nowrap">
              <TextInput label="Name" placeholder="region" {...form.getInputProps(`filters.${i}.name`)} />
              <Select label="Type" w={120} data={PARAM_TYPES} {...form.getInputProps(`filters.${i}.type`)} />
              <TextInput label="Label" {...form.getInputProps(`filters.${i}.label`)} />
              <TextInput label="Default" {...form.getInputProps(`filters.${i}.default`)} />
              <ActionIcon color="red" variant="subtle" mb={4} onClick={() => removeFilter(i)}>
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          ))}

          <Group justify="flex-end" mt="sm">
            <Button variant="subtle" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={createMutation.isPending || updateMutation.isPending}>
              {isEdit ? 'Update' : 'Create'}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
