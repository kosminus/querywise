import { ActionIcon, Menu, Tooltip } from '@mantine/core';
import { IconDotsVertical } from '@tabler/icons-react';
import { useAuth } from '../../context/auth';
import type { Role } from '../../types/auth';

// Mirror of versioning_service._ALLOWED_TRANSITIONS (source -> targets).
const ALLOWED: Record<string, string[]> = {
  draft: ['in_review', 'certified'],
  in_review: ['draft', 'certified'],
  certified: ['draft', 'deprecated'],
  deprecated: ['draft'],
};

// Minimum role required to move *to* a status (mirror of _ROLE_FOR_TARGET).
const ROLE_FOR_TARGET: Record<string, Role> = {
  draft: 'editor',
  in_review: 'editor',
  certified: 'admin',
  deprecated: 'admin',
};

const ROLE_RANK: Record<Role, number> = { viewer: 1, editor: 2, admin: 3 };

const ACTION_LABEL: Record<string, string> = {
  draft: 'Revert to draft',
  in_review: 'Submit for review',
  certified: 'Certify',
  deprecated: 'Deprecate',
};

export interface StatusActionsProps {
  status: string;
  onTransition: (target: string, reason?: string) => void;
}

/** A role-aware menu offering the valid certification-lifecycle transitions. */
export function StatusActions({ status, onTransition }: StatusActionsProps) {
  const { role } = useAuth();
  const myRank = role ? ROLE_RANK[role] : 0;
  const targets = (ALLOWED[status] ?? []).filter(
    (t) => myRank >= ROLE_RANK[ROLE_FOR_TARGET[t]],
  );

  if (targets.length === 0) return null;

  return (
    <Menu position="bottom-end" withArrow>
      <Menu.Target>
        <Tooltip label="Lifecycle">
          <ActionIcon variant="subtle" aria-label="Certification actions">
            <IconDotsVertical size={16} />
          </ActionIcon>
        </Tooltip>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Certification</Menu.Label>
        {targets.map((t) => (
          <Menu.Item
            key={t}
            onClick={() => {
              const reason = window.prompt(`${ACTION_LABEL[t]} — reason (optional):`) ?? undefined;
              onTransition(t, reason || undefined);
            }}
          >
            {ACTION_LABEL[t] ?? t}
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
