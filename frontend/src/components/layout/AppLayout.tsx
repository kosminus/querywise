import {
  ActionIcon,
  AppShell,
  Badge,
  Group,
  Menu,
  NavLink,
  Select,
  Text,
  Title,
} from '@mantine/core';
import {
  IconMessageQuestion,
  IconDatabase,
  IconBook,
  IconChartBar,
  IconVocabulary,
  IconFileText,
  IconHistory,
  IconLogout,
  IconUserCircle,
} from '@tabler/icons-react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { EmbeddingStatusBanner } from '../common/EmbeddingStatusBanner';
import { useAuth } from '../../context/auth';
import type { Role } from '../../types/auth';

const NAV_ITEMS = [
  { label: 'Query', path: '/query', icon: IconMessageQuestion },
  { label: 'Connections', path: '/connections', icon: IconDatabase },
  { label: 'Glossary', path: '/glossary', icon: IconBook },
  { label: 'Metrics', path: '/metrics', icon: IconChartBar },
  { label: 'Dictionary', path: '/dictionary', icon: IconVocabulary },
  { label: 'Knowledge', path: '/knowledge', icon: IconFileText },
  { label: 'History', path: '/history', icon: IconHistory },
];

const ROLE_COLOR: Record<Role, string> = {
  admin: 'grape',
  editor: 'blue',
  viewer: 'gray',
};

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, workspaces, activeWorkspace, role, setActiveWorkspace, logout } = useAuth();

  async function handleLogout() {
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: 'sm' }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Title order={3} fw={700}>
              QueryWise
            </Title>
            <Text size="sm" c="dimmed" visibleFrom="sm">
              Ask questions in plain English
            </Text>
          </Group>

          <Group gap="sm" wrap="nowrap">
            {workspaces.length > 0 && (
              <Select
                size="xs"
                w={200}
                aria-label="Active workspace"
                data={workspaces.map((w) => ({ value: w.team_id, label: w.team_name }))}
                value={activeWorkspace?.team_id ?? null}
                onChange={(v) => v && setActiveWorkspace(v)}
                allowDeselect={false}
                checkIconPosition="right"
              />
            )}
            {role && (
              <Badge color={ROLE_COLOR[role]} variant="light" visibleFrom="sm">
                {role}
              </Badge>
            )}
            <Menu position="bottom-end" withArrow>
              <Menu.Target>
                <ActionIcon variant="subtle" size="lg" aria-label="Account menu">
                  <IconUserCircle size={24} stroke={1.5} />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>{user?.email ?? 'Account'}</Menu.Label>
                <Menu.Item
                  leftSection={<IconLogout size={16} />}
                  onClick={handleLogout}
                >
                  Sign out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            label={item.label}
            leftSection={<item.icon size={20} stroke={1.5} />}
            active={location.pathname === item.path}
            onClick={() => navigate(item.path)}
            variant="light"
            mb={4}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <EmbeddingStatusBanner />
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
