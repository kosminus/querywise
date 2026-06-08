import { Code, Modal, Text, Timeline, Loader, Group } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { CertificationBadge } from './CertificationBadge';
import type { SemanticVersion } from '../../types/api';

export interface VersionHistoryProps {
  opened: boolean;
  onClose: () => void;
  title: string;
  /** Fetches the version changelog; only called while the modal is open. */
  queryKey: unknown[];
  fetchVersions: () => Promise<SemanticVersion[]>;
}

/** A modal rendering an entity's certification/version changelog as a timeline. */
export function VersionHistory({
  opened,
  onClose,
  title,
  queryKey,
  fetchVersions,
}: VersionHistoryProps) {
  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: fetchVersions,
    enabled: opened,
  });

  return (
    <Modal opened={opened} onClose={onClose} title={`History — ${title}`} size="lg">
      {isLoading && (
        <Group justify="center" py="lg">
          <Loader />
        </Group>
      )}
      {data && data.length === 0 && (
        <Text c="dimmed" size="sm">
          No version history yet. Edits and certification changes appear here.
        </Text>
      )}
      {data && data.length > 0 && (
        <Timeline active={data.length} bulletSize={18} lineWidth={2}>
          {data.map((v) => (
            <Timeline.Item key={v.id} title={`v${v.version}`}>
              <Group gap={6} mb={4}>
                <CertificationBadge status={v.status} size="xs" />
                <Text size="xs" c="dimmed">
                  {new Date(v.created_at).toLocaleString()}
                </Text>
              </Group>
              {v.change_reason && (
                <Text size="sm" mb={4}>
                  {v.change_reason}
                </Text>
              )}
              <Code block fz="xs">
                {JSON.stringify(v.snapshot, null, 2)}
              </Code>
            </Timeline.Item>
          ))}
        </Timeline>
      )}
    </Modal>
  );
}
