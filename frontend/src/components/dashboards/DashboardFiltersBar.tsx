import { Button, Group, Paper, Text } from '@mantine/core';
import { IconFilter } from '@tabler/icons-react';
import type { DashboardFilter } from '../../types/api';
import { ParamInputs } from '../common/ParamInputs';

/**
 * Renders the dashboard's filter controls. Values are held by the parent and
 * passed to every tile run; only tiles whose SQL references a {{name}} use it.
 */
export function DashboardFiltersBar({
  filters,
  values,
  onChange,
  onApply,
}: {
  filters: DashboardFilter[];
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
  onApply: () => void;
}) {
  if (filters.length === 0) return null;

  return (
    <Paper withBorder p="md">
      <Group gap="xs" mb="xs">
        <IconFilter size={16} />
        <Text fw={500} size="sm">
          Filters
        </Text>
      </Group>
      <Group align="flex-end">
        <ParamInputs params={filters} values={values} onChange={onChange} inline />
        <Button variant="light" onClick={onApply}>
          Apply
        </Button>
      </Group>
    </Paper>
  );
}
