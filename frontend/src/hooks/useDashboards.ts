import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { dashboardsApi } from '../api/dashboardsApi';
import type { Dashboard } from '../types/api';

export function useDashboards() {
  return useQuery({ queryKey: ['dashboards'], queryFn: dashboardsApi.list });
}

export function useDashboard(id: string | undefined) {
  return useQuery({
    queryKey: ['dashboards', id],
    queryFn: () => dashboardsApi.get(id!),
    enabled: !!id,
  });
}

export function useCreateDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Dashboard>) => dashboardsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboards'] }),
  });
}

export function useUpdateDashboard(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Dashboard>) => dashboardsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dashboards'] });
      qc.invalidateQueries({ queryKey: ['dashboards', id] });
    },
  });
}

export function useDeleteDashboard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => dashboardsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboards'] }),
  });
}

export function useAddTile(dashboardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof dashboardsApi.addTile>[1]) =>
      dashboardsApi.addTile(dashboardId, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboards', dashboardId] }),
  });
}

export function useDeleteTile(dashboardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tileId: string) => dashboardsApi.deleteTile(dashboardId, tileId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboards', dashboardId] }),
  });
}
