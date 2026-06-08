import { useState } from 'react';
import {
  Stack,
  Title,
  Group,
  Text,
  Badge,
  Button,
  Select,
  Table,
  Alert,
  Loader,
  Code,
  Collapse,
  ActionIcon,
  Tooltip,
} from '@mantine/core';
import { IconDownload, IconChevronRight, IconChevronDown } from '@tabler/icons-react';
import { useAuth } from '../context/auth';
import { useAuditEvents, useAuditEventTypes } from '../hooks/useAudit';
import { auditApi } from '../api/auditApi';
import type { AuditEvent } from '../types/api';

const PAGE_SIZE = 100;

// Colour an event by its subject/verb. Blocked/failed actions stand out red.
function eventColor(eventType: string): string {
  if (eventType.includes('blocked') || eventType.includes('failed')) return 'red';
  if (eventType.startsWith('auth.')) return 'blue';
  if (eventType.startsWith('connection.')) return 'grape';
  if (eventType.startsWith('query.')) return 'teal';
  return 'gray';
}

// A one-line gist of the payload for the table row (full JSON is in the expand).
function summarize(payload: Record<string, unknown>): string {
  const keys = ['name', 'question', 'reason', 'connection_id', 'email'];
  for (const k of keys) {
    if (payload[k]) return `${k}: ${String(payload[k])}`;
  }
  const entries = Object.entries(payload).filter(([k]) => k !== 'request_id');
  return entries.length ? `${entries[0][0]}: ${String(entries[0][1])}` : '—';
}

function AuditRow({ event }: { event: AuditEvent }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Table.Tr style={{ cursor: 'pointer' }} onClick={() => setOpen((o) => !o)}>
        <Table.Td>
          <ActionIcon variant="subtle" size="sm" aria-label="Toggle details">
            {open ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />}
          </ActionIcon>
        </Table.Td>
        <Table.Td>
          <Text size="xs" c="dimmed">
            {new Date(event.created_at).toLocaleString()}
          </Text>
        </Table.Td>
        <Table.Td>
          <Badge size="sm" variant="light" color={eventColor(event.event_type)}>
            {event.event_type}
          </Badge>
        </Table.Td>
        <Table.Td>
          <Text size="xs" ff="monospace">
            {event.actor_id ? event.actor_id.slice(0, 8) : 'system'}
          </Text>
        </Table.Td>
        <Table.Td>
          <Text size="xs" lineClamp={1}>
            {summarize(event.payload)}
          </Text>
        </Table.Td>
      </Table.Tr>
      <Table.Tr>
        <Table.Td colSpan={5} p={0} style={{ border: open ? undefined : 'none' }}>
          <Collapse in={open}>
            <Code block m="xs">
              {JSON.stringify(event.payload, null, 2)}
            </Code>
          </Collapse>
        </Table.Td>
      </Table.Tr>
    </>
  );
}

export function AuditPage() {
  const { role } = useAuth();
  const isAdmin = role === 'admin';

  const [eventType, setEventType] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [exporting, setExporting] = useState(false);

  const typesQuery = useAuditEventTypes(isAdmin);
  const { data: events, isLoading } = useAuditEvents(
    { event_type: eventType || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE },
    isAdmin,
  );

  if (!isAdmin) {
    return (
      <Stack gap="md">
        <Title order={2}>Audit Log</Title>
        <Alert color="yellow" title="Admins only">
          The audit log is restricted to workspace administrators.
        </Alert>
      </Stack>
    );
  }

  async function handleExport() {
    setExporting(true);
    try {
      await auditApi.exportCsv({ event_type: eventType || undefined });
    } finally {
      setExporting(false);
    }
  }

  const hasNext = (events?.length ?? 0) === PAGE_SIZE;

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Audit Log</Title>
        <Button
          leftSection={<IconDownload size={16} />}
          variant="light"
          onClick={handleExport}
          loading={exporting}
        >
          Export CSV
        </Button>
      </Group>

      <Group>
        <Select
          placeholder="All event types"
          clearable
          searchable
          w={260}
          data={typesQuery.data ?? []}
          value={eventType}
          onChange={(v) => {
            setEventType(v);
            setPage(0);
          }}
        />
      </Group>

      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      ) : !events || events.length === 0 ? (
        <Alert color="blue">No audit events for this filter.</Alert>
      ) : (
        <>
          <Table highlightOnHover verticalSpacing="xs" striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={40} />
                <Table.Th>Time</Table.Th>
                <Table.Th>Event</Table.Th>
                <Table.Th>Actor</Table.Th>
                <Table.Th>Details</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {events.map((e) => (
                <AuditRow key={e.id} event={e} />
              ))}
            </Table.Tbody>
          </Table>

          <Group justify="space-between">
            <Text size="xs" c="dimmed">
              Page {page + 1}
            </Text>
            <Group gap="xs">
              <Tooltip label="Previous page" disabled={page === 0}>
                <Button
                  size="xs"
                  variant="default"
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  Previous
                </Button>
              </Tooltip>
              <Button
                size="xs"
                variant="default"
                disabled={!hasNext}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </Group>
          </Group>
        </>
      )}
    </Stack>
  );
}
