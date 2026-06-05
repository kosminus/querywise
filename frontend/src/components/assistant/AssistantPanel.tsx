import { useRef, useState } from 'react';
import {
  Paper,
  Stack,
  Group,
  Textarea,
  Button,
  Text,
  TextInput,
  TagsInput,
  Alert,
  Loader,
  Badge,
  ActionIcon,
  ScrollArea,
} from '@mantine/core';
import { IconSend, IconCheck, IconPlayerPlay, IconX, IconSparkles } from '@tabler/icons-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { assistantApi } from '../../api/assistantApi';
import { glossaryApi, metricsApi, dictionaryApi } from '../../api/glossaryApi';
import { knowledgeApi } from '../../api/knowledgeApi';
import { queryApi } from '../../api/queryApi';
import { QueryResultView } from '../query/QueryResultView';
import type {
  AssistantChatMessage,
  DictionaryDraft,
  GlossaryDraft,
  KnowledgeDraft,
  MetricDraft,
  QueryResult,
  SqlPreviewPayload,
} from '../../types/api';

export function AssistantPanel({ connectionId }: { connectionId: string | null }) {
  const [messages, setMessages] = useState<AssistantChatMessage[]>([]);
  const [input, setInput] = useState('');
  const viewport = useRef<HTMLDivElement>(null);

  const scrollToBottom = () =>
    requestAnimationFrame(() =>
      viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: 'smooth' }),
    );

  const sendMutation = useMutation({
    mutationFn: (message: string) =>
      assistantApi.send({
        connection_id: connectionId!,
        message,
        // Send prior turns as plain {role, content}; cards aren't part of LLM history.
        history: messages.map((m) => ({ role: m.role, content: m.content })),
      }),
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.message, action: data.action },
      ]);
      scrollToBottom();
    },
  });

  const handleSend = () => {
    const message = input.trim();
    if (!message || !connectionId) return;
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setInput('');
    sendMutation.mutate(message);
    scrollToBottom();
  };

  return (
    <Paper withBorder p="md">
      <Group gap="xs" mb="sm">
        <IconSparkles size={18} color="var(--mantine-color-violet-5)" />
        <Text fw={600}>Assistant</Text>
        <Text size="xs" c="dimmed">
          ask questions or add glossary terms in plain language
        </Text>
      </Group>

      {messages.length > 0 && (
        <ScrollArea.Autosize mah={420} mb="sm" viewportRef={viewport}>
          <Stack gap="sm">
            {messages.map((m, i) => (
              <ChatTurn key={i} message={m} connectionId={connectionId!} />
            ))}
          </Stack>
        </ScrollArea.Autosize>
      )}

      {sendMutation.isPending && (
        <Group gap="xs" mb="sm">
          <Loader size="xs" />
          <Text size="sm" c="dimmed">
            Thinking…
          </Text>
        </Group>
      )}

      {sendMutation.isError && (
        <Alert color="red" mb="sm">
          {(sendMutation.error as Error).message}
        </Alert>
      )}

      <Textarea
        placeholder={
          connectionId
            ? 'e.g. "Add a glossary term: NPL means loans where stage = 3"'
            : 'Select a connection first'
        }
        autosize
        minRows={1}
        maxRows={4}
        value={input}
        onChange={(e) => setInput(e.currentTarget.value)}
        disabled={!connectionId}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
      />
      <Group justify="flex-end" mt="xs">
        <Button
          leftSection={<IconSend size={16} />}
          onClick={handleSend}
          loading={sendMutation.isPending}
          disabled={!connectionId || !input.trim()}
        >
          Send
        </Button>
      </Group>
    </Paper>
  );
}

function ChatTurn({
  message,
  connectionId,
}: {
  message: AssistantChatMessage;
  connectionId: string;
}) {
  const isUser = message.role === 'user';
  return (
    <Stack gap="xs">
      <Group justify={isUser ? 'flex-end' : 'flex-start'}>
        <Paper
          withBorder
          p="xs"
          bg={isUser ? 'blue.0' : 'gray.0'}
          maw="85%"
          style={{ whiteSpace: 'pre-wrap' }}
        >
          <Text size="sm">{message.content}</Text>
        </Paper>
      </Group>
      {message.action?.type === 'glossary_draft' && (
        <GlossaryDraftCard draft={message.action.payload} connectionId={connectionId} />
      )}
      {message.action?.type === 'metric_draft' && (
        <MetricDraftCard draft={message.action.payload} connectionId={connectionId} />
      )}
      {message.action?.type === 'dictionary_draft' && (
        <DictionaryDraftCard draft={message.action.payload} />
      )}
      {message.action?.type === 'knowledge_draft' && (
        <KnowledgeDraftCard draft={message.action.payload} connectionId={connectionId} />
      )}
      {message.action?.type === 'sql_preview' && (
        <SqlPreviewCard payload={message.action.payload} connectionId={connectionId} />
      )}
    </Stack>
  );
}

function GlossaryDraftCard({
  draft,
  connectionId,
}: {
  draft: GlossaryDraft;
  connectionId: string;
}) {
  const qc = useQueryClient();
  const [term, setTerm] = useState(draft.term);
  const [definition, setDefinition] = useState(draft.definition);
  const [sqlExpression, setSqlExpression] = useState(draft.sql_expression);
  const [relatedTables, setRelatedTables] = useState<string[]>(draft.related_tables);
  const [relatedColumns, setRelatedColumns] = useState<string[]>(draft.related_columns);
  const [dismissed, setDismissed] = useState(false);

  const createMutation = useMutation({
    mutationFn: () =>
      glossaryApi.create(connectionId, {
        term,
        definition,
        sql_expression: sqlExpression,
        related_tables: relatedTables,
        related_columns: relatedColumns,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['glossary', connectionId] }),
  });

  if (dismissed) return null;

  if (createMutation.isSuccess) {
    return (
      <Alert color="green" icon={<IconCheck size={16} />} title="Glossary term created">
        “{term}” was added to the glossary.
      </Alert>
    );
  }

  return (
    <Paper withBorder p="md" bg="violet.0">
      <Group gap="xs" mb="xs">
        <Badge color="violet" variant="light">
          Glossary draft
        </Badge>
        <Text size="xs" c="dimmed">
          review and confirm
        </Text>
      </Group>
      <Stack gap="xs">
        <TextInput label="Term" value={term} onChange={(e) => setTerm(e.currentTarget.value)} />
        <Textarea
          label="Definition"
          autosize
          minRows={1}
          value={definition}
          onChange={(e) => setDefinition(e.currentTarget.value)}
        />
        <TextInput
          label="SQL expression"
          value={sqlExpression}
          onChange={(e) => setSqlExpression(e.currentTarget.value)}
        />
        <TagsInput label="Related tables" value={relatedTables} onChange={setRelatedTables} />
        <TagsInput label="Related columns" value={relatedColumns} onChange={setRelatedColumns} />
      </Stack>
      {createMutation.isError && (
        <Alert color="red" mt="xs">
          {(createMutation.error as Error).message}
        </Alert>
      )}
      <Group justify="flex-end" mt="md">
        <Button variant="default" leftSection={<IconX size={16} />} onClick={() => setDismissed(true)}>
          Dismiss
        </Button>
        <Button
          color="violet"
          leftSection={<IconCheck size={16} />}
          loading={createMutation.isPending}
          disabled={!term.trim() || !definition.trim() || !sqlExpression.trim()}
          onClick={() => createMutation.mutate()}
        >
          Create term
        </Button>
      </Group>
    </Paper>
  );
}

function MetricDraftCard({
  draft,
  connectionId,
}: {
  draft: MetricDraft;
  connectionId: string;
}) {
  const qc = useQueryClient();
  const [metricName, setMetricName] = useState(draft.metric_name);
  const [displayName, setDisplayName] = useState(draft.display_name);
  const [description, setDescription] = useState(draft.description);
  const [sqlExpression, setSqlExpression] = useState(draft.sql_expression);
  const [aggregationType, setAggregationType] = useState(draft.aggregation_type);
  const [relatedTables, setRelatedTables] = useState<string[]>(draft.related_tables);
  const [dimensions, setDimensions] = useState<string[]>(draft.dimensions);
  const [dismissed, setDismissed] = useState(false);

  const createMutation = useMutation({
    mutationFn: () =>
      metricsApi.create(connectionId, {
        metric_name: metricName,
        display_name: displayName,
        description,
        sql_expression: sqlExpression,
        aggregation_type: aggregationType,
        related_tables: relatedTables,
        dimensions,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['metrics', connectionId] }),
  });

  if (dismissed) return null;
  if (createMutation.isSuccess) {
    return (
      <Alert color="green" icon={<IconCheck size={16} />} title="Metric created">
        “{displayName}” was added to your metrics.
      </Alert>
    );
  }

  return (
    <Paper withBorder p="md" bg="teal.0">
      <Group gap="xs" mb="xs">
        <Badge color="teal" variant="light">
          Metric draft
        </Badge>
        <Text size="xs" c="dimmed">
          review and confirm
        </Text>
      </Group>
      <Stack gap="xs">
        <Group grow>
          <TextInput
            label="Display name"
            value={displayName}
            onChange={(e) => setDisplayName(e.currentTarget.value)}
          />
          <TextInput
            label="Metric name"
            value={metricName}
            onChange={(e) => setMetricName(e.currentTarget.value)}
          />
        </Group>
        <Textarea
          label="Description"
          autosize
          minRows={1}
          value={description}
          onChange={(e) => setDescription(e.currentTarget.value)}
        />
        <TextInput
          label="SQL expression"
          value={sqlExpression}
          onChange={(e) => setSqlExpression(e.currentTarget.value)}
        />
        <TextInput
          label="Aggregation type"
          value={aggregationType}
          onChange={(e) => setAggregationType(e.currentTarget.value)}
        />
        <TagsInput label="Related tables" value={relatedTables} onChange={setRelatedTables} />
        <TagsInput label="Dimensions" value={dimensions} onChange={setDimensions} />
      </Stack>
      {createMutation.isError && (
        <Alert color="red" mt="xs">
          {(createMutation.error as Error).message}
        </Alert>
      )}
      <Group justify="flex-end" mt="md">
        <Button variant="default" leftSection={<IconX size={16} />} onClick={() => setDismissed(true)}>
          Dismiss
        </Button>
        <Button
          color="teal"
          leftSection={<IconCheck size={16} />}
          loading={createMutation.isPending}
          disabled={!metricName.trim() || !displayName.trim() || !sqlExpression.trim()}
          onClick={() => createMutation.mutate()}
        >
          Create metric
        </Button>
      </Group>
    </Paper>
  );
}

function DictionaryDraftCard({ draft }: { draft: DictionaryDraft }) {
  const qc = useQueryClient();
  const [entries, setEntries] = useState(draft.entries);
  const [dismissed, setDismissed] = useState(false);

  const createMutation = useMutation({
    mutationFn: async () => {
      for (let i = 0; i < entries.length; i++) {
        await dictionaryApi.create(draft.column_id, { ...entries[i], sort_order: i });
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dictionary', draft.column_id] }),
  });

  const updateEntry = (i: number, patch: Partial<(typeof entries)[number]>) =>
    setEntries((prev) => prev.map((e, j) => (j === i ? { ...e, ...patch } : e)));
  const removeEntry = (i: number) => setEntries((prev) => prev.filter((_, j) => j !== i));

  if (dismissed) return null;
  if (createMutation.isSuccess) {
    return (
      <Alert color="green" icon={<IconCheck size={16} />} title="Dictionary entries created">
        Added {entries.length} value mapping{entries.length === 1 ? '' : 's'} to{' '}
        <b>
          {draft.table_name}.{draft.column_name}
        </b>
        .
      </Alert>
    );
  }

  return (
    <Paper withBorder p="md" bg="grape.0">
      <Group gap="xs" mb="xs">
        <Badge color="grape" variant="light">
          Dictionary draft
        </Badge>
        <Text size="sm" fw={500}>
          {draft.table_name}.{draft.column_name}
        </Text>
      </Group>
      <Stack gap="xs">
        {entries.map((entry, i) => (
          <Group key={i} gap="xs" align="flex-end" wrap="nowrap">
            <TextInput
              label={i === 0 ? 'Raw value' : undefined}
              w={110}
              value={entry.raw_value}
              onChange={(e) => updateEntry(i, { raw_value: e.currentTarget.value })}
            />
            <TextInput
              label={i === 0 ? 'Display value' : undefined}
              style={{ flex: 1 }}
              value={entry.display_value}
              onChange={(e) => updateEntry(i, { display_value: e.currentTarget.value })}
            />
            <TextInput
              label={i === 0 ? 'Description' : undefined}
              style={{ flex: 1 }}
              value={entry.description}
              onChange={(e) => updateEntry(i, { description: e.currentTarget.value })}
            />
            <ActionIcon
              variant="subtle"
              color="red"
              onClick={() => removeEntry(i)}
              aria-label="Remove entry"
            >
              <IconX size={16} />
            </ActionIcon>
          </Group>
        ))}
      </Stack>
      {createMutation.isError && (
        <Alert color="red" mt="xs">
          {(createMutation.error as Error).message}
        </Alert>
      )}
      <Group justify="flex-end" mt="md">
        <Button variant="default" leftSection={<IconX size={16} />} onClick={() => setDismissed(true)}>
          Dismiss
        </Button>
        <Button
          color="grape"
          leftSection={<IconCheck size={16} />}
          loading={createMutation.isPending}
          disabled={
            entries.length === 0 ||
            entries.some((e) => !e.raw_value.trim() || !e.display_value.trim())
          }
          onClick={() => createMutation.mutate()}
        >
          Create {entries.length} entr{entries.length === 1 ? 'y' : 'ies'}
        </Button>
      </Group>
    </Paper>
  );
}

function KnowledgeDraftCard({
  draft,
  connectionId,
}: {
  draft: KnowledgeDraft;
  connectionId: string;
}) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(draft.title);
  const [content, setContent] = useState(draft.content);
  const [sourceUrl, setSourceUrl] = useState(draft.source_url);
  const [dismissed, setDismissed] = useState(false);

  const createMutation = useMutation({
    mutationFn: () =>
      knowledgeApi.create(connectionId, {
        title,
        content,
        source_url: sourceUrl.trim() || undefined,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledge', connectionId] }),
  });

  if (dismissed) return null;
  if (createMutation.isSuccess) {
    return (
      <Alert color="green" icon={<IconCheck size={16} />} title="Knowledge added">
        “{title}” was added and will be chunked + embedded for retrieval.
      </Alert>
    );
  }

  return (
    <Paper withBorder p="md" bg="cyan.0">
      <Group gap="xs" mb="xs">
        <Badge color="cyan" variant="light">
          Knowledge draft
        </Badge>
        <Text size="xs" c="dimmed">
          review and confirm
        </Text>
      </Group>
      <Stack gap="xs">
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
        <Textarea
          label="Content"
          autosize
          minRows={3}
          maxRows={12}
          value={content}
          onChange={(e) => setContent(e.currentTarget.value)}
        />
        <TextInput
          label="Source URL (optional)"
          value={sourceUrl}
          onChange={(e) => setSourceUrl(e.currentTarget.value)}
        />
      </Stack>
      {createMutation.isError && (
        <Alert color="red" mt="xs">
          {(createMutation.error as Error).message}
        </Alert>
      )}
      <Group justify="flex-end" mt="md">
        <Button variant="default" leftSection={<IconX size={16} />} onClick={() => setDismissed(true)}>
          Dismiss
        </Button>
        <Button
          color="cyan"
          leftSection={<IconCheck size={16} />}
          loading={createMutation.isPending}
          disabled={!title.trim() || !content.trim()}
          onClick={() => createMutation.mutate()}
        >
          Add knowledge
        </Button>
      </Group>
    </Paper>
  );
}

function SqlPreviewCard({
  payload,
  connectionId,
}: {
  payload: SqlPreviewPayload;
  connectionId: string;
}) {
  const [sql, setSql] = useState(payload.sql);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [cancelled, setCancelled] = useState(false);

  const executeMutation = useMutation({
    mutationFn: () => queryApi.executeSql({ connection_id: connectionId, sql }),
    onSuccess: (data) => setResult(data),
  });

  if (result) return <QueryResultView result={result} />;
  if (cancelled) return null;

  return (
    <Paper withBorder p="md">
      <Group gap="xs" mb="xs">
        <Badge variant="light">SQL preview</Badge>
        <Text size="xs" c="dimmed">
          edit if needed, then run
        </Text>
      </Group>
      {payload.explanation && (
        <Text size="sm" c="dimmed" mb="xs">
          {payload.explanation}
        </Text>
      )}
      <Textarea
        autosize
        minRows={2}
        value={sql}
        onChange={(e) => setSql(e.currentTarget.value)}
        styles={{ input: { fontFamily: 'monospace' } }}
      />
      {executeMutation.isError && (
        <Alert color="red" mt="xs">
          {(executeMutation.error as Error).message}
        </Alert>
      )}
      <Group justify="flex-end" mt="md">
        <Button variant="default" leftSection={<IconX size={16} />} onClick={() => setCancelled(true)}>
          Cancel
        </Button>
        <Button
          color="green"
          leftSection={<IconPlayerPlay size={16} />}
          loading={executeMutation.isPending}
          disabled={!sql.trim()}
          onClick={() => executeMutation.mutate()}
        >
          Execute
        </Button>
      </Group>
    </Paper>
  );
}
