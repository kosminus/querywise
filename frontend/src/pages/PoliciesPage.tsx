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
  Textarea,
  MultiSelect,
  NumberInput,
  Switch,
  Table,
  ActionIcon,
  Select,
  Alert,
  Loader,
  Code,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconPencil, IconTrash, IconPlus } from '@tabler/icons-react';
import { useConnections } from '../hooks/useConnections';
import {
  usePolicies,
  useCreatePolicy,
  useUpdatePolicy,
  useDeletePolicy,
} from '../hooks/usePolicies';
import type { DataPolicy } from '../types/api';

// "table: condition" per line <-> { table: condition }
function filtersToText(f: Record<string, string>): string {
  return Object.entries(f)
    .map(([k, v]) => `${k}: ${v}`)
    .join('\n');
}
function textToFilters(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split('\n')) {
    const idx = line.indexOf(':');
    if (idx > 0) {
      const k = line.slice(0, idx).trim();
      const v = line.slice(idx + 1).trim();
      if (k && v) out[k] = v;
    }
  }
  return out;
}
const csv = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean);

export function PoliciesPage() {
  const { data: connections } = useConnections();
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const connOptions = (connections ?? []).map((c) => ({ value: c.id, label: c.name }));
  if (!connectionId && connOptions.length > 0) setConnectionId(connOptions[0].value);

  const { data: policies, isLoading } = usePolicies(connectionId ?? undefined);
  const del = useDeletePolicy(connectionId ?? '');
  const [editing, setEditing] = useState<DataPolicy | null>(null);
  const [open, setOpen] = useState(false);

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>Data Policies</Title>
        <Button
          leftSection={<IconPlus size={16} />}
          disabled={!connectionId}
          onClick={() => {
            setEditing(null);
            setOpen(true);
          }}
        >
          New policy
        </Button>
      </Group>

      <Group>
        <Select
          label="Connection"
          w={260}
          data={connOptions}
          value={connectionId}
          onChange={setConnectionId}
        />
      </Group>

      <Alert color="gray" variant="light">
        Policies are enforced before a query reaches the database: row/runtime caps, allow/block
        tables, blocked columns, PII masking, and row-level filters — merged most-restrictively per
        role.
      </Alert>

      {isLoading ? (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      ) : !policies || policies.length === 0 ? (
        <Alert color="blue">No policies on this connection.</Alert>
      ) : (
        <Table highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Name</Table.Th>
              <Table.Th>Roles</Table.Th>
              <Table.Th>Rules</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {policies.map((p) => (
              <Table.Tr key={p.id}>
                <Table.Td>
                  <Group gap="xs">
                    <Text size="sm" fw={500}>
                      {p.name}
                    </Text>
                    {!p.enabled && (
                      <Badge size="xs" color="gray" variant="light">
                        disabled
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{p.applies_to_roles.join(', ') || 'all'}</Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    {p.max_rows != null && (
                      <Badge size="xs" variant="light">
                        ≤{p.max_rows} rows
                      </Badge>
                    )}
                    {p.blocked_columns.length > 0 && (
                      <Badge size="xs" color="red" variant="light">
                        {p.blocked_columns.length} blocked col
                      </Badge>
                    )}
                    {p.masked_columns.length > 0 && (
                      <Badge size="xs" color="orange" variant="light">
                        {p.masked_columns.length} masked
                      </Badge>
                    )}
                    {Object.keys(p.row_filters).length > 0 && (
                      <Badge size="xs" color="grape" variant="light">
                        {Object.keys(p.row_filters).length} row filter
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Group gap={4} justify="flex-end" wrap="nowrap">
                    <ActionIcon
                      variant="subtle"
                      onClick={() => {
                        setEditing(p);
                        setOpen(true);
                      }}
                    >
                      <IconPencil size={16} />
                    </ActionIcon>
                    <ActionIcon variant="subtle" color="red" onClick={() => del.mutate(p.id)}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {open && connectionId && (
        <PolicyFormModal
          connectionId={connectionId}
          policy={editing}
          onClose={() => setOpen(false)}
        />
      )}
    </Stack>
  );
}

interface FormValues {
  name: string;
  enabled: boolean;
  priority: number;
  applies_to_roles: string[];
  max_rows: number | '';
  max_runtime_seconds: number | '';
  allowed_tables: string;
  blocked_tables: string;
  blocked_columns: string;
  masked_columns: string;
  row_filters: string;
}

function PolicyFormModal({
  connectionId,
  policy,
  onClose,
}: {
  connectionId: string;
  policy: DataPolicy | null;
  onClose: () => void;
}) {
  const create = useCreatePolicy(connectionId);
  const update = useUpdatePolicy(connectionId);

  const form = useForm<FormValues>({
    initialValues: {
      name: policy?.name ?? '',
      enabled: policy?.enabled ?? true,
      priority: policy?.priority ?? 100,
      applies_to_roles: policy?.applies_to_roles ?? [],
      max_rows: policy?.max_rows ?? '',
      max_runtime_seconds: policy?.max_runtime_seconds ?? '',
      allowed_tables: (policy?.allowed_tables ?? []).join(', '),
      blocked_tables: (policy?.blocked_tables ?? []).join(', '),
      blocked_columns: (policy?.blocked_columns ?? []).join(', '),
      masked_columns: (policy?.masked_columns ?? []).join(', '),
      row_filters: filtersToText(policy?.row_filters ?? {}),
    },
  });

  function submit(v: FormValues) {
    const payload: Partial<DataPolicy> = {
      name: v.name,
      enabled: v.enabled,
      priority: v.priority,
      applies_to_roles: v.applies_to_roles,
      max_rows: v.max_rows === '' ? null : Number(v.max_rows),
      max_runtime_seconds: v.max_runtime_seconds === '' ? null : Number(v.max_runtime_seconds),
      allowed_tables: csv(v.allowed_tables),
      blocked_tables: csv(v.blocked_tables),
      blocked_columns: csv(v.blocked_columns),
      masked_columns: csv(v.masked_columns),
      row_filters: textToFilters(v.row_filters),
    };
    const done = () => onClose();
    if (policy) update.mutate({ id: policy.id, data: payload }, { onSuccess: done });
    else create.mutate(payload, { onSuccess: done });
  }

  return (
    <Modal opened onClose={onClose} title={policy ? 'Edit policy' : 'New policy'} size="lg">
      <form onSubmit={form.onSubmit(submit)}>
        <Stack gap="sm">
          <TextInput label="Name" required {...form.getInputProps('name')} />
          <Group grow>
            <MultiSelect
              label="Applies to roles"
              placeholder="all roles"
              data={['admin', 'editor', 'viewer']}
              {...form.getInputProps('applies_to_roles')}
            />
            <NumberInput label="Priority" {...form.getInputProps('priority')} />
          </Group>
          <Group grow>
            <NumberInput label="Max rows" placeholder="no cap" {...form.getInputProps('max_rows')} />
            <NumberInput
              label="Max runtime (s)"
              placeholder="no cap"
              {...form.getInputProps('max_runtime_seconds')}
            />
          </Group>
          <Group grow>
            <TextInput
              label="Allowed tables"
              description="Comma-separated; empty = no restriction"
              {...form.getInputProps('allowed_tables')}
            />
            <TextInput label="Blocked tables" {...form.getInputProps('blocked_tables')} />
          </Group>
          <Group grow>
            <TextInput
              label="Blocked columns"
              description="Blocks the query if referenced"
              {...form.getInputProps('blocked_columns')}
            />
            <TextInput
              label="Masked columns"
              description="Redacted in results (star-safe)"
              {...form.getInputProps('masked_columns')}
            />
          </Group>
          <Textarea
            label="Row filters"
            description="One per line: table: <SQL boolean condition>"
            autosize
            minRows={2}
            placeholder={'orders: region = \'EU\''}
            {...form.getInputProps('row_filters')}
          />
          <Text size="xs" c="dimmed">
            Names may be bare (<Code>email</Code>) or qualified (<Code>users.email</Code>).
          </Text>
          <Switch label="Enabled" {...form.getInputProps('enabled', { type: 'checkbox' })} />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending || update.isPending}>
              {policy ? 'Save' : 'Create'}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
