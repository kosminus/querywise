import { AppShell, NavLink, Group, Title, Text } from '@mantine/core';
import {
  IconMessageQuestion,
  IconDatabase,
  IconBook,
  IconChartBar,
  IconVocabulary,
  IconFileText,
  IconHistory,
} from '@tabler/icons-react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { EmbeddingStatusBanner } from '../common/EmbeddingStatusBanner';

const NAV_ITEMS = [
  { label: 'Query', path: '/query', icon: IconMessageQuestion },
  { label: 'Connections', path: '/connections', icon: IconDatabase },
  { label: 'Glossary', path: '/glossary', icon: IconBook },
  { label: 'Metrics', path: '/metrics', icon: IconChartBar },
  { label: 'Dictionary', path: '/dictionary', icon: IconVocabulary },
  { label: 'Knowledge', path: '/knowledge', icon: IconFileText },
  { label: 'History', path: '/history', icon: IconHistory },
];

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: 'sm' }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md">
          <Title order={3} fw={700}>
            QueryWise
          </Title>
          <Text size="sm" c="dimmed">
            Ask questions in plain English
          </Text>
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
