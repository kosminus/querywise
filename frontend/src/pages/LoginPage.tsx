import { useState } from 'react';
import {
  Alert,
  Anchor,
  Button,
  Center,
  Divider,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useQuery } from '@tanstack/react-query';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { authApi } from '../api/authApi';
import { useAuth } from '../context/auth';
import type { MagicLinkResponse } from '../types/auth';

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { refresh, isAuthenticated } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [name, setName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [magicLink, setMagicLink] = useState<MagicLinkResponse | null>(null);

  const { data: providers } = useQuery({
    queryKey: ['auth-providers'],
    queryFn: authApi.providers,
    staleTime: Infinity,
  });

  // Already signed in (or auth disabled) — bounce to where they came from.
  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/';
  if (isAuthenticated) {
    return <Navigate to={redirectTo} replace />;
  }

  async function afterAuth() {
    await refresh();
    navigate(redirectTo, { replace: true });
  }

  async function handlePasswordSubmit() {
    setSubmitting(true);
    try {
      if (mode === 'register') {
        await authApi.register(email, password, name || undefined);
      } else {
        await authApi.login(email, password);
      }
      await afterAuth();
    } catch (err) {
      notifications.show({
        color: 'red',
        title: mode === 'register' ? 'Registration failed' : 'Login failed',
        message: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleMagicLink() {
    if (!email) {
      notifications.show({ color: 'red', message: 'Enter your email first.' });
      return;
    }
    setSubmitting(true);
    try {
      setMagicLink(await authApi.requestMagicLink(email));
    } catch (err) {
      notifications.show({
        color: 'red',
        title: 'Could not send magic link',
        message: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDevVerify(token: string) {
    setSubmitting(true);
    try {
      await authApi.verifyMagicLink(token);
      await afterAuth();
    } catch (err) {
      notifications.show({
        color: 'red',
        title: 'Verification failed',
        message: err instanceof Error ? err.message : 'The link may have expired.',
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Center mih="100vh" bg="var(--mantine-color-gray-0)">
      <Paper withBorder shadow="md" p="xl" radius="md" w={400}>
        <Stack>
          <div>
            <Title order={2} fw={700}>
              QueryWise
            </Title>
            <Text size="sm" c="dimmed">
              {mode === 'register' ? 'Create your account' : 'Sign in to continue'}
            </Text>
          </div>

          {providers?.disable_auth && (
            <Alert color="yellow" title="Authentication disabled">
              This deployment runs with <code>DISABLE_AUTH</code>. You are signed in
              automatically as the default admin.
            </Alert>
          )}

          {providers?.supports_password && (
            <>
              <TextInput
                label="Email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.currentTarget.value)}
                required
              />
              {mode === 'register' && (
                <TextInput
                  label="Name"
                  placeholder="Your name"
                  value={name}
                  onChange={(e) => setName(e.currentTarget.value)}
                />
              )}
              <PasswordInput
                label="Password"
                value={password}
                onChange={(e) => setPassword(e.currentTarget.value)}
                required
              />
              <Button onClick={handlePasswordSubmit} loading={submitting} fullWidth>
                {mode === 'register' ? 'Create account' : 'Sign in'}
              </Button>
              <Text size="xs" ta="center">
                {mode === 'register' ? 'Already have an account? ' : 'No account yet? '}
                <Anchor
                  component="button"
                  type="button"
                  onClick={() => setMode(mode === 'register' ? 'login' : 'register')}
                >
                  {mode === 'register' ? 'Sign in' : 'Create one'}
                </Anchor>
              </Text>
            </>
          )}

          {providers?.supports_password && providers?.supports_magic_link && (
            <Divider label="or" labelPosition="center" />
          )}

          {providers?.supports_magic_link && (
            <>
              {!providers.supports_password && (
                <TextInput
                  label="Email"
                  placeholder="you@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.currentTarget.value)}
                  required
                />
              )}
              <Button variant="light" onClick={handleMagicLink} loading={submitting} fullWidth>
                Email me a magic link
              </Button>
            </>
          )}

          {magicLink?.sent && (
            <Alert color="blue" title="Magic link sent">
              <Stack gap="xs">
                <Text size="sm">Check your email for a sign-in link.</Text>
                {magicLink.dev_token && (
                  <Button
                    size="xs"
                    variant="outline"
                    onClick={() => handleDevVerify(magicLink.dev_token!)}
                    loading={submitting}
                  >
                    Dev: continue without email
                  </Button>
                )}
              </Stack>
            </Alert>
          )}
        </Stack>
      </Paper>
    </Center>
  );
}
