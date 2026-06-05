import { createContext, useContext } from 'react';
import type { Role, User, WorkspaceMembership } from '../types/auth';

export interface AuthContextValue {
  user: User | null;
  workspaces: WorkspaceMembership[];
  activeWorkspace: WorkspaceMembership | null;
  role: Role | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  /** Re-fetch /auth/me (call after a successful login). */
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
  setActiveWorkspace: (teamId: string) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
