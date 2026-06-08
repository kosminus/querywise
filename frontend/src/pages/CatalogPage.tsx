import { useEffect, useState } from 'react';
import {
  Alert,
  Badge,
  Card,
  Checkbox,
  Drawer,
  Grid,
  Group,
  Loader,
  Paper,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { IconSearch } from '@tabler/icons-react';
import { useConnections } from '../hooks/useConnections';
import { useCatalogFacets, useCatalogSearch } from '../hooks/useCatalog';
import { catalogApi } from '../api/catalogApi';
import { metricsApi } from '../api/glossaryApi';
import { savedQueriesApi } from '../api/savedQueriesApi';
import { CertificationBadge } from '../components/common/CertificationBadge';
import type { CatalogHit, LineageRef } from '../types/api';

const TYPE_COLOR: Record<string, string> = {
  table: 'blue',
  column: 'cyan',
  metric: 'grape',
  glossary: 'teal',
  sample_query: 'orange',
  saved_query: 'indigo',
  knowledge: 'gray',
};

const TYPE_LABEL: Record<string, string> = {
  table: 'Table',
  column: 'Column',
  metric: 'Metric',
  glossary: 'Glossary',
  sample_query: 'Sample query',
  saved_query: 'Saved query',
  knowledge: 'Knowledge',
};

const ALL_TYPES = Object.keys(TYPE_COLOR);

export function CatalogPage() {
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [schema, setSchema] = useState<string | null>(null);
  const [selected, setSelected] = useState<CatalogHit | null>(null);

  const { data: connections } = useConnections();
  const connOptions = connections?.map((c) => ({ value: c.id, label: c.name })) ?? [];
  if (!connectionId && connOptions.length > 0) {
    setConnectionId(connOptions[0].value);
  }

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(t);
  }, [search]);

  const { data: facets } = useCatalogFacets(connectionId ?? undefined);
  const { data: hits, isLoading } = useCatalogSearch(connectionId ?? undefined, {
    q: debounced,
    types: selectedTypes,
    status: status ?? undefined,
    schema: schema ?? undefined,
  });

  return (
    <Stack gap="md">
      <Title order={2}>Data Catalog</Title>

      <Group>
        <Select
          label="Connection"
          data={connOptions}
          value={connectionId}
          onChange={setConnectionId}
          w={260}
        />
      </Group>

      <Grid>
        {/* Facet sidebar */}
        <Grid.Col span={{ base: 12, sm: 3 }}>
          <Stack gap="md">
            <Paper withBorder p="sm" radius="md">
              <Text fw={600} size="sm" mb="xs">
                Type
              </Text>
              <Checkbox.Group value={selectedTypes} onChange={setSelectedTypes}>
                <Stack gap={6}>
                  {ALL_TYPES.map((t) => (
                    <Checkbox key={t} value={t} label={TYPE_LABEL[t]} size="xs" />
                  ))}
                </Stack>
              </Checkbox.Group>
            </Paper>

            <Select
              label="Status"
              placeholder="Any"
              clearable
              data={['draft', 'in_review', 'certified', 'deprecated']}
              value={status}
              onChange={setStatus}
            />

            <Select
              label="Schema"
              placeholder="Any"
              clearable
              data={facets?.schemas ?? []}
              value={schema}
              onChange={setSchema}
            />

            {facets && (
              <Paper withBorder p="sm" radius="md">
                <Text fw={600} size="sm" mb="xs">
                  By status
                </Text>
                <Stack gap={4}>
                  {Object.entries(facets.status_counts).map(([st, n]) => (
                    <Group key={st} justify="space-between">
                      <CertificationBadge status={st} size="xs" />
                      <Text size="xs" c="dimmed">
                        {n}
                      </Text>
                    </Group>
                  ))}
                </Stack>
              </Paper>
            )}
          </Stack>
        </Grid.Col>

        {/* Results */}
        <Grid.Col span={{ base: 12, sm: 9 }}>
          <Stack gap="sm">
            <TextInput
              placeholder="Search tables, columns, metrics, glossary, knowledge…"
              leftSection={<IconSearch size={16} />}
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
            />

            {isLoading && (
              <Group justify="center" py="xl">
                <Loader />
              </Group>
            )}

            {hits && hits.length === 0 && (
              <Alert color="blue">No results. Try a different search or widen the filters.</Alert>
            )}

            {hits?.map((hit) => (
              <Card
                key={`${hit.type}:${hit.id}`}
                withBorder
                radius="md"
                padding="sm"
                style={{ cursor: 'pointer' }}
                onClick={() => setSelected(hit)}
              >
                <Group justify="space-between" wrap="nowrap">
                  <Stack gap={2} style={{ minWidth: 0 }}>
                    <Group gap={6}>
                      <Badge size="xs" variant="light" color={TYPE_COLOR[hit.type]}>
                        {TYPE_LABEL[hit.type] ?? hit.type}
                      </Badge>
                      <Text fw={600} truncate>
                        {hit.name}
                      </Text>
                      {hit.status && <CertificationBadge status={hit.status} size="xs" />}
                    </Group>
                    {hit.context && (
                      <Text size="xs" c="dimmed">
                        {hit.context}
                      </Text>
                    )}
                    {hit.description && (
                      <Text size="sm" c="dimmed" lineClamp={1}>
                        {hit.description}
                      </Text>
                    )}
                  </Stack>
                  <Badge size="xs" variant="outline" color="gray">
                    {hit.match_reason}
                  </Badge>
                </Group>
              </Card>
            ))}
          </Stack>
        </Grid.Col>
      </Grid>

      {connectionId && selected && (
        <CatalogDetailDrawer
          connectionId={connectionId}
          hit={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </Stack>
  );
}

function LineageList({ refs }: { refs: LineageRef[] }) {
  if (refs.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        No lineage recorded.
      </Text>
    );
  }
  return (
    <Stack gap={4}>
      {refs.map((r) => (
        <Group key={r.id} gap={6}>
          <Badge size="xs" variant="light" color={r.ref_kind === 'table' ? 'blue' : 'cyan'}>
            {r.ref_kind}
          </Badge>
          <Text size="sm">
            {r.schema_name ? `${r.schema_name}.` : ''}
            {r.table_name}
            {r.column_name ? `.${r.column_name}` : ''}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}

function CatalogDetailDrawer({
  connectionId,
  hit,
  onClose,
}: {
  connectionId: string;
  hit: CatalogHit;
  onClose: () => void;
}) {
  // "Touches" — for artifacts that have SQL (saved query / metric).
  const touches = useQuery({
    queryKey: ['lineage', 'touches', connectionId, hit.type, hit.id],
    queryFn: () =>
      hit.type === 'saved_query'
        ? savedQueriesApi.lineage(connectionId, hit.id)
        : metricsApi.lineage(connectionId, hit.id),
    enabled: hit.type === 'saved_query' || hit.type === 'metric',
  });

  // "Depended on by" — for tables/columns, find artifacts referencing them.
  const dependents = useQuery({
    queryKey: ['lineage', 'dependents', connectionId, hit.type, hit.name, hit.context],
    queryFn: () =>
      catalogApi.lineageImpact(
        connectionId,
        hit.type === 'column' ? (hit.context?.split('.').pop() ?? '') : hit.name,
        hit.type === 'column' ? hit.name : undefined,
      ),
    enabled: hit.type === 'table' || hit.type === 'column',
  });

  return (
    <Drawer opened onClose={onClose} position="right" size="md" title={hit.name}>
      <Stack gap="md">
        <Group gap={6}>
          <Badge variant="light" color={TYPE_COLOR[hit.type]}>
            {TYPE_LABEL[hit.type] ?? hit.type}
          </Badge>
          {hit.status && <CertificationBadge status={hit.status} />}
        </Group>
        {hit.context && (
          <Text size="sm" c="dimmed">
            {hit.context}
          </Text>
        )}
        {hit.description && <Text size="sm">{hit.description}</Text>}

        {(hit.type === 'saved_query' || hit.type === 'metric') && (
          <div>
            <Text fw={600} size="sm" mb="xs">
              Touches
            </Text>
            {touches.isLoading ? <Loader size="sm" /> : <LineageList refs={touches.data ?? []} />}
          </div>
        )}

        {(hit.type === 'table' || hit.type === 'column') && (
          <div>
            <Text fw={600} size="sm" mb="xs">
              Depended on by
            </Text>
            {dependents.isLoading ? (
              <Loader size="sm" />
            ) : dependents.data && dependents.data.length > 0 ? (
              <Stack gap={4}>
                {dependents.data.map((r) => (
                  <Group key={r.id} gap={6}>
                    <Badge size="xs" variant="light" color={TYPE_COLOR[r.artifact_type] ?? 'gray'}>
                      {TYPE_LABEL[r.artifact_type] ?? r.artifact_type}
                    </Badge>
                    <Text size="sm">{r.artifact_id.slice(0, 8)}…</Text>
                  </Group>
                ))}
              </Stack>
            ) : (
              <Text size="sm" c="dimmed">
                Nothing depends on this yet.
              </Text>
            )}
          </div>
        )}
      </Stack>
    </Drawer>
  );
}
