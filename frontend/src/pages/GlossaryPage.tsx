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
  Code,
  TagsInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconPlus, IconTrash, IconEdit, IconHistory } from '@tabler/icons-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { glossaryApi } from '../api/glossaryApi';
import { useConnections } from '../hooks/useConnections';
import type { GlossaryTerm } from '../types/api';
import { CertificationBadge } from '../components/common/CertificationBadge';
import { StatusActions } from '../components/common/StatusActions';
import { VersionHistory } from '../components/common/VersionHistory';

export function GlossaryPage() {
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [editingTerm, setEditingTerm] = useState<GlossaryTerm | null>(null);
  const [historyFor, setHistoryFor] = useState<GlossaryTerm | null>(null);

  const { data: connections } = useConnections();
  const qc = useQueryClient();

  const connOptions =
    connections?.map((c) => ({ value: c.id, label: c.name })) ?? [];
  if (!connectionId && connOptions.length > 0) {
    setConnectionId(connOptions[0].value);
  }

  const { data: terms, isLoading } = useQuery({
    queryKey: ['glossary', connectionId],
    queryFn: () => glossaryApi.list(connectionId!),
    enabled: !!connectionId,
  });

  const deleteMutation = useMutation({
    mutationFn: ({ connId, termId }: { connId: string; termId: string }) =>
      glossaryApi.delete(connId, termId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['glossary', connectionId] }),
  });

  const transitionMutation = useMutation({
    mutationFn: ({ termId, status, reason }: { termId: string; status: string; reason?: string }) =>
      glossaryApi.transitionStatus(connectionId!, termId, status, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['glossary', connectionId] });
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
        <Title order={2}>Business Glossary</Title>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={() => setAddOpen(true)}
          disabled={!connectionId}
        >
          Add Term
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

      {terms?.length === 0 && (
        <Alert color="blue">
          No glossary terms yet. Add business terms to improve SQL generation.
        </Alert>
      )}

      {terms && terms.length > 0 && (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Term</Table.Th>
              <Table.Th>Definition</Table.Th>
              <Table.Th>SQL Expression</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th w={130}>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {terms.map((term: GlossaryTerm) => (
              <Table.Tr key={term.id}>
                <Table.Td>
                  <Text fw={500}>{term.term}</Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" lineClamp={2}>
                    {term.definition}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Code>{term.sql_expression}</Code>
                </Table.Td>
                <Table.Td>
                  <Group gap={6}>
                    <CertificationBadge status={term.status} />
                    <Text size="xs" c="dimmed">
                      v{term.version}
                    </Text>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    <Tooltip label="Edit">
                      <ActionIcon
                        variant="subtle"
                        size="sm"
                        onClick={() => setEditingTerm(term)}
                      >
                        <IconEdit size={14} />
                      </ActionIcon>
                    </Tooltip>
                    <Tooltip label="Version history">
                      <ActionIcon variant="subtle" size="sm" onClick={() => setHistoryFor(term)}>
                        <IconHistory size={14} />
                      </ActionIcon>
                    </Tooltip>
                    <StatusActions
                      status={term.status}
                      onTransition={(status, reason) =>
                        transitionMutation.mutate({ termId: term.id, status, reason })
                      }
                    />
                    <Tooltip label="Delete">
                      <ActionIcon
                        variant="subtle"
                        color="red"
                        size="sm"
                        onClick={() => {
                          if (confirm(`Delete "${term.term}"?`))
                            deleteMutation.mutate({
                              connId: connectionId!,
                              termId: term.id,
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
        <GlossaryFormModal
          opened={addOpen || !!editingTerm}
          onClose={() => {
            setAddOpen(false);
            setEditingTerm(null);
          }}
          connectionId={connectionId}
          term={editingTerm}
        />
      )}

      {connectionId && historyFor && (
        <VersionHistory
          opened={!!historyFor}
          onClose={() => setHistoryFor(null)}
          title={historyFor.term}
          queryKey={['glossaryVersions', connectionId, historyFor.id]}
          fetchVersions={() => glossaryApi.versions(connectionId, historyFor.id)}
        />
      )}
    </Stack>
  );
}

function GlossaryFormModal({
  opened,
  onClose,
  connectionId,
  term,
}: {
  opened: boolean;
  onClose: () => void;
  connectionId: string;
  term: GlossaryTerm | null;
}) {
  const qc = useQueryClient();
  const isEdit = !!term;

  const form = useForm({
    initialValues: {
      term: '',
      definition: '',
      sql_expression: '',
      related_tables: [] as string[],
      related_columns: [] as string[],
    },
  });

  useEffect(() => {
    if (term) {
      form.setValues({
        term: term.term,
        definition: term.definition,
        sql_expression: term.sql_expression ?? '',
        related_tables: term.related_tables ?? [],
        related_columns: term.related_columns ?? [],
      });
    } else {
      form.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [term]);

  const mutation = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      isEdit
        ? glossaryApi.update(connectionId, term!.id, values)
        : glossaryApi.create(connectionId, values),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['glossary', connectionId] });
      notifications.show({
        title: isEdit ? 'Term updated' : 'Term created',
        message: `"${form.values.term}" saved`,
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
      title={isEdit ? 'Edit Glossary Term' : 'Add Glossary Term'}
      size="lg"
    >
      <form onSubmit={form.onSubmit((v) => mutation.mutate(v))}>
        <Stack gap="sm">
          <TextInput label="Term" required {...form.getInputProps('term')} />
          <Textarea
            label="Definition"
            required
            autosize
            minRows={2}
            {...form.getInputProps('definition')}
          />
          <Textarea
            label="SQL Expression"
            required
            placeholder="e.g. exposures.ead or stage = 1"
            autosize
            minRows={2}
            {...form.getInputProps('sql_expression')}
          />
          <TagsInput
            label="Related Tables"
            placeholder="Type table name and press Enter"
            {...form.getInputProps('related_tables')}
          />
          <TagsInput
            label="Related Columns"
            placeholder="Type column name and press Enter"
            {...form.getInputProps('related_columns')}
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
