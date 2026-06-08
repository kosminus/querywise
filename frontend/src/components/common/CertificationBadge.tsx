import { Badge } from '@mantine/core';

const STATUS_COLOR: Record<string, string> = {
  draft: 'gray',
  in_review: 'yellow',
  certified: 'green',
  deprecated: 'red',
};

const STATUS_LABEL: Record<string, string> = {
  draft: 'draft',
  in_review: 'in review',
  certified: 'certified',
  deprecated: 'deprecated',
};

export function CertificationBadge({ status, size = 'sm' }: { status: string; size?: string }) {
  return (
    <Badge size={size} variant="light" color={STATUS_COLOR[status] ?? 'gray'}>
      {STATUS_LABEL[status] ?? status}
    </Badge>
  );
}
