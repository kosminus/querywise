import {
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  Stack,
  TextInput,
  Textarea,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useCreateSavedQuery } from '../../hooks/useSavedQueries';
import type { ParamDef } from '../../types/api';

/** Extract {{name}} placeholders from SQL into string param defs. */
function detectParams(sql: string): ParamDef[] {
  const seen = new Set<string>();
  const defs: ParamDef[] = [];
  const re = /\{\{\s*(\w+)\s*\}\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(sql)) !== null) {
    if (!seen.has(m[1])) {
      seen.add(m[1]);
      defs.push({ name: m[1], type: 'string', label: m[1] });
    }
  }
  return defs;
}

export function SaveQueryModal({
  opened,
  onClose,
  connectionId,
  question,
  sql,
}: {
  opened: boolean;
  onClose: () => void;
  connectionId: string;
  question: string;
  sql: string;
}) {
  const createMutation = useCreateSavedQuery(connectionId);
  const params = detectParams(sql);

  const form = useForm({
    initialValues: { name: question.slice(0, 80) || 'Untitled query', description: '' },
  });

  const handleSubmit = (values: { name: string; description: string }) => {
    createMutation.mutate(
      {
        name: values.name,
        description: values.description || null,
        nl_question: question || null,
        pinned_sql: sql,
        params,
      },
      {
        onSuccess: () => {
          notifications.show({
            title: 'Query saved',
            message: `"${values.name}" is now in Saved Queries`,
            color: 'green',
          });
          form.reset();
          onClose();
        },
        onError: (err) =>
          notifications.show({
            title: 'Could not save query',
            message: (err as Error).message,
            color: 'red',
          }),
      },
    );
  };

  return (
    <Modal opened={opened} onClose={onClose} title="Save query" size="lg">
      <form onSubmit={form.onSubmit(handleSubmit)}>
        <Stack gap="sm">
          <TextInput label="Name" required {...form.getInputProps('name')} />
          <Textarea label="Description" autosize minRows={2} {...form.getInputProps('description')} />
          {params.length > 0 && (
            <Alert color="blue" title="Detected parameters">
              <Group gap="xs">
                {params.map((p) => (
                  <Badge key={p.name} variant="light">
                    {`{{${p.name}}}`}
                  </Badge>
                ))}
              </Group>
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="subtle" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={createMutation.isPending}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
