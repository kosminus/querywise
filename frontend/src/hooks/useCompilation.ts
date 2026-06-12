import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compilationApi, type StartRunOptions } from '../api/compilationApi';

export function useCompilationRuns(connectionId: string | undefined) {
  return useQuery({
    queryKey: ['compilation-runs', connectionId],
    queryFn: () => compilationApi.listRuns(connectionId!),
    enabled: !!connectionId,
    // Poll while a run is queued/running (mirrors useEmbeddingStatus).
    refetchInterval: query => {
      const data = query.state.data;
      if (!data) return false;
      const active = data.some(r => r.status === 'queued' || r.status === 'running');
      return active ? 2000 : false;
    },
  });
}

export function useCompilationFindings(
  connectionId: string | undefined,
  filters: { status?: string; kind?: string } = {},
) {
  return useQuery({
    queryKey: ['compilation-findings', connectionId, filters],
    queryFn: () => compilationApi.listFindings(connectionId!, filters),
    enabled: !!connectionId,
  });
}

function useInvalidate(connectionId: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ['compilation-findings', connectionId] });
    qc.invalidateQueries({ queryKey: ['compilation-runs', connectionId] });
  };
}

export function useStartCompilation(connectionId: string) {
  const invalidate = useInvalidate(connectionId);
  return useMutation({
    mutationFn: (options: StartRunOptions) => compilationApi.startRun(connectionId, options),
    onSuccess: invalidate,
  });
}

export function useAcceptFinding(connectionId: string) {
  const invalidate = useInvalidate(connectionId);
  return useMutation({
    mutationFn: (findingId: string) => compilationApi.accept(connectionId, findingId),
    onSuccess: invalidate,
  });
}

export function useDismissFinding(connectionId: string) {
  const invalidate = useInvalidate(connectionId);
  return useMutation({
    mutationFn: (findingId: string) => compilationApi.dismiss(connectionId, findingId),
    onSuccess: invalidate,
  });
}

export function useBulkReview(connectionId: string) {
  const invalidate = useInvalidate(connectionId);
  return useMutation({
    mutationFn: ({ ids, action }: { ids: string[]; action: 'accept' | 'dismiss' }) =>
      compilationApi.bulk(connectionId, ids, action),
    onSuccess: invalidate,
  });
}
