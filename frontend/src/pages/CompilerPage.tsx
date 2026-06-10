import { useMemo, useState } from 'react';
import {
  Accordion,
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Loader,
  Progress,
  Select,
  Slider,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { IconSparkles } from '@tabler/icons-react';
import { useConnections } from '../hooks/useConnections';
import {
  useAcceptFinding,
  useBulkReview,
  useCompilationFindings,
  useCompilationRuns,
  useDismissFinding,
  useStartCompilation,
} from '../hooks/useCompilation';
import { FindingCard } from '../components/compiler/FindingCard';
import type { CompilationFinding, CompilationRun } from '../types/api';

const KIND_LABEL: Record<CompilationFinding['kind'], string> = {
  relationship: 'Inferred join paths',
  metric: 'Metric candidates',
  dictionary: 'Value dictionaries',
  glossary: 'Glossary entities',
  data_policy_row_filter: 'Row-filter policies (tenant scoping)',
  data_policy_masking: 'PII masking',
  dead_table: 'Dead tables',
  fanout_warning: 'Fan-out warnings',
};

const KIND_ORDER = Object.keys(KIND_LABEL) as CompilationFinding['kind'][];

function RunBanner({ run }: { run: CompilationRun }) {
  if (run.status === 'failed') {
    return (
      <Alert color="red" title="Compilation failed">
        {run.error}
      </Alert>
    );
  }
  if (run.status === 'queued' || run.status === 'running') {
    const p = run.progress;
    return (
      <Alert color="blue" title="Compiling semantic layer…">
        <Stack gap={6}>
          <Text size="sm">{p?.stage || 'Starting…'}</Text>
          <Progress value={p ? (p.completed / Math.max(p.total, 1)) * 100 : 5} animated />
        </Stack>
      </Alert>
    );
  }
  const sources = run.stats.sources_available ?? {};
  const missing = Object.entries(sources)
    .filter(([, available]) => !available)
    .map(([name]) => name);
  return (
    <Alert color="green" title="Compilation complete">
      <Text size="sm">
        Examined {run.stats.tables_examined ?? 0} tables, {run.stats.views_examined ?? 0} views,{' '}
        {run.stats.logged_queries_examined ?? 0} logged queries.
      </Text>
      {missing.length > 0 && (
        <Text size="sm" c="dimmed">
          Unavailable evidence sources: {missing.join(', ')} — confidence is reduced where these
          would have helped. (pg_stats needs ANALYZE; query logs need the pg_stat_statements
          extension.)
        </Text>
      )}
    </Alert>
  );
}

export function CompilerPage() {
  const { data: connections } = useConnections();
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const connOptions = (connections ?? []).map(c => ({ value: c.id, label: c.name }));
  if (!connectionId && connOptions.length > 0) setConnectionId(connOptions[0].value);

  const [llmEnabled, setLlmEnabled] = useState(true);
  const [minConfidence, setMinConfidence] = useState(0.5);
  const [statusFilter, setStatusFilter] = useState<string>('proposed');

  const { data: runs } = useCompilationRuns(connectionId ?? undefined);
  const latestRun = runs?.[0];
  const runActive = latestRun?.status === 'queued' || latestRun?.status === 'running';

  const { data: findings, isLoading } = useCompilationFindings(connectionId ?? undefined, {
    status: statusFilter || undefined,
  });

  const start = useStartCompilation(connectionId ?? '');
  const accept = useAcceptFinding(connectionId ?? '');
  const dismiss = useDismissFinding(connectionId ?? '');
  const bulk = useBulkReview(connectionId ?? '');

  const grouped = useMemo(() => {
    const groups = new Map<CompilationFinding['kind'], CompilationFinding[]>();
    for (const finding of findings ?? []) {
      const list = groups.get(finding.kind) ?? [];
      list.push(finding);
      groups.set(finding.kind, list);
    }
    return groups;
  }, [findings]);

  const busy = accept.isPending || dismiss.isPending || bulk.isPending;

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Semantic Layer Compiler</Title>
        <Button
          leftSection={<IconSparkles size={16} />}
          disabled={!connectionId || runActive}
          loading={start.isPending}
          onClick={() =>
            start.mutate({ llm_enabled: llmEnabled, min_confidence: minConfidence })
          }
        >
          Compile semantic layer
        </Button>
      </Group>

      <Alert color="gray" variant="light">
        Introspects the connected database — schema, column statistics, view definitions, and
        query logs — and proposes draft semantic-layer objects with evidence and confidence.
        Nothing is created until you accept a finding; accepted objects land as{' '}
        <Badge size="sm" variant="light" color="gray">
          draft
        </Badge>{' '}
        for normal certification.
      </Alert>

      <Group align="flex-end">
        <Select
          label="Connection"
          w={260}
          data={connOptions}
          value={connectionId}
          onChange={setConnectionId}
        />
        <Stack gap={2} w={200}>
          <Text size="sm" fw={500}>
            Min confidence: {(minConfidence * 100).toFixed(0)}%
          </Text>
          <Slider
            value={minConfidence}
            onChange={setMinConfidence}
            min={0.3}
            max={0.9}
            step={0.05}
            label={v => `${(v * 100).toFixed(0)}%`}
          />
        </Stack>
        <Checkbox
          label="LLM naming pass"
          checked={llmEnabled}
          onChange={e => setLlmEnabled(e.currentTarget.checked)}
          mb={6}
        />
        <Select
          label="Show"
          w={150}
          data={[
            { value: 'proposed', label: 'Proposed' },
            { value: 'accepted', label: 'Accepted' },
            { value: 'dismissed', label: 'Dismissed' },
          ]}
          value={statusFilter}
          onChange={v => setStatusFilter(v ?? 'proposed')}
        />
      </Group>

      {latestRun && <RunBanner run={latestRun} />}

      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      ) : !findings || findings.length === 0 ? (
        <Alert color="blue">
          No {statusFilter} findings on this connection. Run the compiler to generate proposals.
        </Alert>
      ) : (
        <Accordion multiple defaultValue={KIND_ORDER} variant="separated">
          {KIND_ORDER.filter(kind => grouped.has(kind)).map(kind => {
            const group = grouped.get(kind)!;
            const proposed = group.filter(f => f.status === 'proposed');
            return (
              <Accordion.Item key={kind} value={kind}>
                <Accordion.Control>
                  <Group gap="xs">
                    <Text fw={600}>{KIND_LABEL[kind]}</Text>
                    <Badge size="sm" variant="light">
                      {group.length}
                    </Badge>
                  </Group>
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack gap="xs">
                    {proposed.length > 1 && (
                      <Group gap="xs">
                        <Button
                          size="compact-xs"
                          variant="light"
                          color="green"
                          disabled={busy}
                          onClick={() =>
                            bulk.mutate({ ids: proposed.map(f => f.id), action: 'accept' })
                          }
                        >
                          Accept all ({proposed.length})
                        </Button>
                        <Button
                          size="compact-xs"
                          variant="light"
                          color="gray"
                          disabled={busy}
                          onClick={() =>
                            bulk.mutate({ ids: proposed.map(f => f.id), action: 'dismiss' })
                          }
                        >
                          Dismiss all
                        </Button>
                      </Group>
                    )}
                    {group.map(finding => (
                      <FindingCard
                        key={finding.id}
                        finding={finding}
                        onAccept={id => accept.mutate(id)}
                        onDismiss={id => dismiss.mutate(id)}
                        busy={busy}
                      />
                    ))}
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            );
          })}
        </Accordion>
      )}
    </Stack>
  );
}
