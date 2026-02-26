import { useState } from 'react';
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
  Accordion,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import {
  IconPlus,
  IconTrash,
  IconFileText,
  IconDownload,
} from '@tabler/icons-react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { knowledgeApi } from '../api/knowledgeApi';
import { useConnections } from '../hooks/useConnections';
import type { KnowledgeDocument, KnowledgeDocumentDetail } from '../types/api';

export function KnowledgePage() {
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [viewDocId, setViewDocId] = useState<string | null>(null);

  const { data: connections } = useConnections();
  const qc = useQueryClient();

  const connOptions =
    connections?.map((c) => ({ value: c.id, label: c.name })) ?? [];
  if (!connectionId && connOptions.length > 0) {
    setConnectionId(connOptions[0].value);
  }

  const { data: documents, isLoading } = useQuery({
    queryKey: ['knowledge', connectionId],
    queryFn: () => knowledgeApi.list(connectionId!),
    enabled: !!connectionId,
  });

  const { data: docDetail } = useQuery({
    queryKey: ['knowledge', connectionId, 'detail', viewDocId],
    queryFn: () => knowledgeApi.get(connectionId!, viewDocId!),
    enabled: !!connectionId && !!viewDocId,
  });

  const deleteMutation = useMutation({
    mutationFn: ({
      connId,
      documentId,
    }: {
      connId: string;
      documentId: string;
    }) => knowledgeApi.delete(connId, documentId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['knowledge', connectionId] }),
  });

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Knowledge Base</Title>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={() => setAddOpen(true)}
          disabled={!connectionId}
        >
          Import Document
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

      {documents?.length === 0 && (
        <Alert color="blue">
          No knowledge documents yet. Import business documentation to improve
          SQL generation with domain context.
        </Alert>
      )}

      {documents && documents.length > 0 && (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Title</Table.Th>
              <Table.Th>Source</Table.Th>
              <Table.Th>Chunks</Table.Th>
              <Table.Th>Imported</Table.Th>
              <Table.Th w={80}>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {documents.map((doc: KnowledgeDocument) => (
              <Table.Tr
                key={doc.id}
                style={{ cursor: 'pointer' }}
                onClick={() =>
                  setViewDocId(viewDocId === doc.id ? null : doc.id)
                }
              >
                <Table.Td>
                  <Group gap={8}>
                    <IconFileText size={16} />
                    <Text fw={500}>{doc.title}</Text>
                  </Group>
                </Table.Td>
                <Table.Td>
                  {doc.source_url ? (
                    <Text
                      size="sm"
                      c="dimmed"
                      lineClamp={1}
                      maw={200}
                    >
                      {doc.source_url}
                    </Text>
                  ) : (
                    <Text size="sm" c="dimmed">
                      Manual input
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <Badge size="sm" variant="light">
                    {doc.chunk_count} chunks
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">
                    {new Date(doc.created_at).toLocaleDateString()}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Tooltip label="Delete">
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Delete "${doc.title}"?`))
                          deleteMutation.mutate({
                            connId: connectionId!,
                            documentId: doc.id,
                          });
                      }}
                    >
                      <IconTrash size={14} />
                    </ActionIcon>
                  </Tooltip>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {viewDocId && docDetail && (
        <ChunkViewer detail={docDetail} />
      )}

      {connectionId && (
        <ImportModal
          opened={addOpen}
          onClose={() => setAddOpen(false)}
          connectionId={connectionId}
        />
      )}
    </Stack>
  );
}

function ChunkViewer({ detail }: { detail: KnowledgeDocumentDetail }) {
  return (
    <Stack gap="xs">
      <Title order={4}>
        Chunks from &ldquo;{detail.title}&rdquo;
      </Title>
      <Accordion variant="separated">
        {detail.chunks
          .sort((a, b) => a.chunk_index - b.chunk_index)
          .map((chunk) => (
            <Accordion.Item
              key={chunk.id}
              value={chunk.id}
            >
              <Accordion.Control>
                <Text size="sm">
                  Chunk {chunk.chunk_index + 1} &mdash;{' '}
                  {chunk.content.slice(0, 80)}...
                </Text>
              </Accordion.Control>
              <Accordion.Panel>
                <Text
                  size="sm"
                  style={{ whiteSpace: 'pre-wrap' }}
                >
                  {chunk.content}
                </Text>
              </Accordion.Panel>
            </Accordion.Item>
          ))}
      </Accordion>
    </Stack>
  );
}

function ImportModal({
  opened,
  onClose,
  connectionId,
}: {
  opened: boolean;
  onClose: () => void;
  connectionId: string;
}) {
  const qc = useQueryClient();

  const form = useForm({
    initialValues: {
      title: '',
      content: '',
      source_url: '',
    },
  });

  const mutation = useMutation({
    mutationFn: (values: {
      title: string;
      content: string;
      source_url: string;
    }) =>
      knowledgeApi.create(connectionId, {
        title: values.title,
        content: values.content,
        source_url: values.source_url || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['knowledge', connectionId] });
      notifications.show({
        title: 'Document imported',
        message: `"${form.values.title}" imported and chunked`,
        color: 'green',
      });
      form.reset();
      onClose();
    },
  });

  const fetchMutation = useMutation({
    mutationFn: (url: string) => knowledgeApi.fetchUrl(url),
    onSuccess: (data) => {
      form.setFieldValue('content', data.content);
      if (data.title && !form.values.title) {
        form.setFieldValue('title', data.title);
      }
      notifications.show({
        title: 'Content fetched',
        message: 'Page content loaded into the text area',
        color: 'blue',
      });
    },
  });

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Import Knowledge Document"
      size="lg"
    >
      <form onSubmit={form.onSubmit((v) => mutation.mutate(v))}>
        <Stack gap="sm">
          <TextInput
            label="Title"
            required
            placeholder="e.g. IFRS 9 Staging Rules"
            {...form.getInputProps('title')}
          />
          <Group align="flex-end" gap="xs">
            <TextInput
              label="Source URL"
              placeholder="https://confluence.example.com/page/..."
              style={{ flex: 1 }}
              {...form.getInputProps('source_url')}
            />
            <Tooltip label="Fetch page content">
              <Button
                variant="light"
                leftSection={<IconDownload size={16} />}
                loading={fetchMutation.isPending}
                disabled={!form.values.source_url}
                onClick={() =>
                  fetchMutation.mutate(form.values.source_url)
                }
              >
                Fetch
              </Button>
            </Tooltip>
          </Group>
          <Textarea
            label="Content"
            required
            placeholder="Paste the text content here or fetch from URL above..."
            autosize
            minRows={8}
            maxRows={20}
            {...form.getInputProps('content')}
          />
          {(mutation.isError || fetchMutation.isError) && (
            <Alert color="red">
              {(mutation.error as Error)?.message ??
                (fetchMutation.error as Error)?.message ??
                'Operation failed'}
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="subtle" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              Import
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
