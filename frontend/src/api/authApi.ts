import { api } from './client';
import type { AuthProviderInfo, MagicLinkResponse, Me, User } from '../types/auth';

export const authApi = {
  providers: () => api.get<AuthProviderInfo>('/auth/providers').then((r) => r.data),
  me: () => api.get<Me>('/auth/me').then((r) => r.data),
  login: (email: string, password: string) =>
    api.post<User>('/auth/login', { email, password }).then((r) => r.data),
  register: (email: string, password: string, name?: string) =>
    api.post<User>('/auth/register', { email, password, name }).then((r) => r.data),
  requestMagicLink: (email: string) =>
    api.post<MagicLinkResponse>('/auth/magic-link', { email }).then((r) => r.data),
  verifyMagicLink: (token: string) =>
    api.post<User>('/auth/magic-link/verify', { token }).then((r) => r.data),
  logout: () => api.post('/auth/logout').then((r) => r.data),
};
