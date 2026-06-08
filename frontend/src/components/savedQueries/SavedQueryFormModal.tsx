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
import { useCreateSavedQuery, useUpdateSavedQuery } from '../../hooks/useSavedQueries';
import type { ParamDef, ParamType, SavedQuery } from '../../types/api';

const PARAM_TYPES: ParamType[] = ['string', 'number', 'date', 'boolean'];

interface FormValues {
  name: string;
  description: string;
  nl_question: string;
  pinned_sql: string;
  status: string;
  is_public: boolean;
  params: ParamDef[];
}

export function SavedQueryFormModal({
  opened,
  onClose,
  connectionId,
  savedQuery,
}: {
  opened: boolean;
  onClose: () => void;
  connectionId: string;
  savedQuery: SavedQuery | null;
}) {
  const isEdit = !!savedQuery;
  const createMutation = useCreateSavedQuery(connectionId);
  const updateMutation = useUpdateSavedQuery(connectionId);

  const form = useForm<FormValues>({
    initialValues: {
      name: '',
      description: '',
      nl_question: '',
      pinned_sql: '',
      status: 'draft',
      is_public: false,
      params: [],
    },
  });

  useEffect(() => {
    if (savedQuery) {
      form.setValues({
        name: savedQuery.name,
        description: savedQuery.description ?? '',
        nl_question: savedQuery.nl_question ?? '',
        pinned_sql: savedQuery.pinned_sql,
        status: savedQuery.status,
        is_public: savedQuery.is_public,
        params: savedQuery.params ?? [],
      });
    } else {
      form.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedQuery, opened]);

  const handleSubmit = (values: FormValues) => {
    const payload = {
      name: values.name,
      description: values.description || null,
      nl_question: values.nl_question || null,
      pinned_sql: values.pinned_sql,
      status: values.status,
      is_public: values.is_public,
      params: values.params,
    };
    const onDone = () => {
      notifications.show({
        title: isEdit ? 'Saved query updated' : 'Saved query created',
        message: `"${values.name}" saved`,
        color: 'green',
      });
      form.reset();
      onClose();
    };
    const onError = (err: unknown) =>
      notifications.show({ title: 'Error', message: (err as Error).message, color: 'red' });

    if (isEdit) {
      updateMutation.mutate({ id: savedQuery!.id, data: payload }, { onSuccess: onDone, onError });
    } else {
      createMutation.mutate(payload, { onSuccess: onDone, onError });
    }
  };

  const addParam = () =>
    form.setFieldValue('params', [
      ...form.values.params,
      { name: '', type: 'string', label: '', default: '' },
    ]);

  const removeParam = (i: number) =>
    form.setFieldValue(
      'params',
      form.values.params.filter((_, idx) => idx !== i),
    );

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={isEdit ? 'Edit Saved Query' : 'New Saved Query'}
      size="xl"
    >
      <form onSubmit={form.onSubmit(handleSubmit)}>
        <Stack gap="sm">
          <TextInput label="Name" required {...form.getInputProps('name')} />
          <Textarea label="Description" autosize minRows={1} {...form.getInputProps('description')} />
          <Textarea
            label="Natural-language question (optional)"
            autosize
            minRows={1}
            {...form.getInputProps('nl_question')}
          />
          <Textarea
            label="Pinned SQL"
            description="Use {{param_name}} for typed parameters."
            required
            autosize
            minRows={4}
            styles={{ input: { fontFamily: 'monospace' } }}
            {...form.getInputProps('pinned_sql')}
          />
          <Group grow>
            <Select
              label="Status"
              data={['draft', 'certified', 'deprecated']}
              {...form.getInputProps('status')}
            />
            <Switch
              label="Shared with workspace"
              mt="lg"
              {...form.getInputProps('is_public', { type: 'checkbox' })}
            />
          </Group>

          <Group justify="space-between" align="center">
            <Text fw={500} size="sm">
              Parameters
            </Text>
            <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={addParam}>
              Add parameter
            </Button>
          </Group>
          {form.values.params.map((_, i) => (
            <Group key={i} align="flex-end" gap="xs" wrap="nowrap">
              <TextInput
                label="Name"
                placeholder="region"
                {...form.getInputProps(`params.${i}.name`)}
              />
              <Select
                label="Type"
                w={120}
                data={PARAM_TYPES}
                {...form.getInputProps(`params.${i}.type`)}
              />
              <TextInput label="Label" {...form.getInputProps(`params.${i}.label`)} />
              <TextInput
                label="Default"
                {...form.getInputProps(`params.${i}.default`)}
              />
              <ActionIcon color="red" variant="subtle" mb={4} onClick={() => removeParam(i)}>
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
