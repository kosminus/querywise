import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi } from '../api/authApi';
import { setActiveWorkspaceId, setUnauthorizedHandler } from '../api/client';
import type { Me } from '../types/auth';
import { AuthContext, type AuthContextValue } from './auth';

const ACTIVE_WS_KEY = 'activeWorkspaceId';

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const meQuery = useQuery<Me>({
    queryKey: ['me'],
    queryFn: authApi.me,
    retry: false,
    staleTime: Infinity,
  });

  const me = meQuery.data ?? null;
  const workspaces = useMemo(() => me?.workspaces ?? [], [me]);

  // Resolve the active workspace: stored choice if still a member, else first.
  const [selectedId, setSelectedId] = useState<string | null>(
    () => (typeof window !== 'undefined' ? localStorage.getItem(ACTIVE_WS_KEY) : null),
  );
  const activeWorkspace =
    workspaces.find((w) => w.team_id === selectedId) ?? workspaces[0] ?? null;

  // Keep the axios header + localStorage in sync with the resolved workspace.
  useEffect(() => {
    setActiveWorkspaceId(activeWorkspace?.team_id ?? null);
    if (activeWorkspace) {
      localStorage.setItem(ACTIVE_WS_KEY, activeWorkspace.team_id);
    }
  }, [activeWorkspace]);

  // On any 401 from a non-auth endpoint, drop the session so guards redirect.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      queryClient.setQueryData(['me'], null);
    });
    return () => setUnauthorizedHandler(null);
  }, [queryClient]);

  const value: AuthContextValue = {
    user: me?.user ?? null,
    workspaces,
    activeWorkspace,
    role: activeWorkspace?.role ?? null,
    isLoading: meQuery.isLoading,
    isAuthenticated: !!me?.user,
    refresh: async () => {
      await queryClient.invalidateQueries({ queryKey: ['me'] });
    },
    logout: async () => {
      try {
        await authApi.logout();
      } finally {
        setActiveWorkspaceId(null);
        queryClient.setQueryData(['me'], null);
        // Workspace-scoped data must not bleed across sessions.
        queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' });
      }
    },
    setActiveWorkspace: (teamId: string) => {
      localStorage.setItem(ACTIVE_WS_KEY, teamId);
      setActiveWorkspaceId(teamId);
      setSelectedId(teamId);
      // Re-fetch everything for the newly selected workspace.
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' });
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
