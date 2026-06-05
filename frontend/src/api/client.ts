import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  // Session is an HTTP-only cookie set by the backend, so credentials must
  // travel with every request (and CORS must allow credentials).
  withCredentials: true,
});

// --- Active workspace -------------------------------------------------------
// Connections + the semantic layer are scoped per workspace. The AuthContext
// keeps this in sync; the request interceptor forwards it as a header.
let activeWorkspaceId: string | null = null;

export function setActiveWorkspaceId(id: string | null) {
  activeWorkspaceId = id;
}

api.interceptors.request.use((config) => {
  if (activeWorkspaceId) {
    config.headers.set('X-Workspace-Id', activeWorkspaceId);
  }
  return config;
});

// --- Unauthorized handling --------------------------------------------------
// On a 401 the session is gone/expired; the AuthContext registers a handler
// here to drop the user and bounce to the login screen.
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

// 401s from the auth endpoints themselves (e.g. a bad login) are expected and
// must not trigger the global logout/redirect.
function isAuthEndpoint(url?: string): boolean {
  return !!url && url.includes('/auth/');
}

// Surface real backend error messages instead of generic "Request failed with status code 500"
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.data?.error) {
      error.message = error.response.data.error;
    }
    if (error.response?.status === 401 && !isAuthEndpoint(error.config?.url) && onUnauthorized) {
      onUnauthorized();
    }
    return Promise.reject(error);
  },
);
