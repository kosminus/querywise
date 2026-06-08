import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { policiesApi } from '../api/policiesApi';
import type { DataPolicy } from '../types/api';

export function usePolicies(connectionId: string | undefined) {
  return useQuery({
    queryKey: ['policies', connectionId],
    queryFn: () => policiesApi.list(connectionId!),
    enabled: !!connectionId,
  });
}

export function useCreatePolicy(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<DataPolicy>) => policiesApi.create(connectionId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['policies', connectionId] }),
  });
}

export function useUpdatePolicy(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<DataPolicy> }) =>
      policiesApi.update(connectionId, id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['policies', connectionId] }),
  });
}

export function useDeletePolicy(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => policiesApi.remove(connectionId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['policies', connectionId] }),
  });
}
