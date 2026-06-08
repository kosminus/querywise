import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { chartsApi, savedQueriesApi } from '../api/savedQueriesApi';
import type { ChartConfig, ChartType, SavedQuery } from '../types/api';

export function useSavedQueries(connectionId: string | undefined) {
  return useQuery({
    queryKey: ['savedQueries', connectionId],
    queryFn: () => savedQueriesApi.list(connectionId!),
    enabled: !!connectionId,
  });
}

export function useCreateSavedQuery(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<SavedQuery>) => savedQueriesApi.create(connectionId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['savedQueries', connectionId] }),
  });
}

export function useUpdateSavedQuery(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<SavedQuery> }) =>
      savedQueriesApi.update(connectionId, id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['savedQueries', connectionId] }),
  });
}

export function useDeleteSavedQuery(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => savedQueriesApi.delete(connectionId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['savedQueries', connectionId] }),
  });
}

export function useCloneSavedQuery(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => savedQueriesApi.clone(connectionId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['savedQueries', connectionId] }),
  });
}

export function useTransitionSavedQueryStatus(connectionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status, reason }: { id: string; status: string; reason?: string }) =>
      savedQueriesApi.transitionStatus(connectionId, id, status, reason),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['savedQueries', connectionId] }),
  });
}

export function useRunSavedQuery(connectionId: string) {
  return useMutation({
    mutationFn: ({
      id,
      params,
      refresh,
    }: {
      id: string;
      params?: Record<string, unknown>;
      refresh?: boolean;
    }) => savedQueriesApi.run(connectionId, id, params ?? {}, refresh ?? false),
  });
}

export function useCharts(connectionId: string | undefined, savedQueryId: string | undefined) {
  return useQuery({
    queryKey: ['charts', connectionId, savedQueryId],
    queryFn: () => chartsApi.list(connectionId!, savedQueryId!),
    enabled: !!connectionId && !!savedQueryId,
  });
}

export function useSaveChart(connectionId: string, savedQueryId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      chartId,
      name,
      chart_type,
      config,
    }: {
      chartId?: string;
      name: string;
      chart_type: ChartType;
      config: ChartConfig;
    }) =>
      chartId
        ? chartsApi.update(connectionId, savedQueryId, chartId, { name, chart_type, config })
        : chartsApi.create(connectionId, savedQueryId, { name, chart_type, config }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['charts', connectionId, savedQueryId] }),
  });
}

export function useDeleteChart(connectionId: string, savedQueryId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (chartId: string) => chartsApi.delete(connectionId, savedQueryId, chartId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['charts', connectionId, savedQueryId] }),
  });
}
