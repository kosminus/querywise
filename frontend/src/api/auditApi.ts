import { api } from './client';
import type { AuditEvent } from '../types/api';

export interface AuditListParams {
  event_type?: string;
  actor_id?: string;
  limit?: number;
  offset?: number;
}

export const auditApi = {
  list: (params: AuditListParams) =>
    api
      .get<AuditEvent[]>('/audit-events', {
        params: {
          event_type: params.event_type || undefined,
          actor_id: params.actor_id || undefined,
          limit: params.limit ?? 100,
          offset: params.offset ?? 0,
        },
      })
      .then((r) => r.data),

  eventTypes: () => api.get<string[]>('/audit-events/event-types').then((r) => r.data),

  // Fetch the CSV through axios (carries the session cookie) and trigger a
  // client-side download, rather than navigating to the raw URL.
  exportCsv: async (params: Pick<AuditListParams, 'event_type' | 'actor_id'>) => {
    const res = await api.get('/audit-events/export', {
      params: {
        event_type: params.event_type || undefined,
        actor_id: params.actor_id || undefined,
      },
      responseType: 'blob',
    });
    const url = URL.createObjectURL(res.data as Blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'audit_events.csv';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
