import { useQuery } from '@tanstack/react-query';
import { auditApi, type AuditListParams } from '../api/auditApi';

export function useAuditEvents(params: AuditListParams, enabled = true) {
  return useQuery({
    queryKey: ['audit', 'events', params],
    queryFn: () => auditApi.list(params),
    enabled,
  });
}

export function useAuditEventTypes(enabled = true) {
  return useQuery({
    queryKey: ['audit', 'event-types'],
    queryFn: () => auditApi.eventTypes(),
    staleTime: Infinity,
    enabled,
  });
}
