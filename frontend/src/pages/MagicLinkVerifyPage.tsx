import { useEffect, useRef, useState } from 'react';
import { Alert, Anchor, Center, Loader, Paper, Stack, Text } from '@mantine/core';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { authApi } from '../api/authApi';
import { useAuth } from '../context/auth';

export function MagicLinkVerifyPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const attempted = useRef(false);

  const token = params.get('token');

  useEffect(() => {
    if (!token || attempted.current) return;
    attempted.current = true;

    authApi
      .verifyMagicLink(token)
      .then(refresh)
      .then(() => navigate('/', { replace: true }))
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : 'This link is invalid or has expired.'),
      );
  }, [token, refresh, navigate]);

  const message = !token ? 'This link is missing its token.' : error;

  return (
    <Center mih="100vh" bg="var(--mantine-color-gray-0)">
      <Paper withBorder shadow="md" p="xl" radius="md" w={400}>
        {message ? (
          <Stack>
            <Alert color="red" title="Sign-in failed">
              {message}
            </Alert>
            <Text size="sm" ta="center">
              <Anchor onClick={() => navigate('/login', { replace: true })}>Back to login</Anchor>
            </Text>
          </Stack>
        ) : (
          <Stack align="center">
            <Loader />
            <Text size="sm" c="dimmed">
              Signing you in…
            </Text>
          </Stack>
        )}
      </Paper>
    </Center>
  );
}
