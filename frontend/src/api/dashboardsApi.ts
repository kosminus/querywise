import { api } from './client';
import type {
  Dashboard,
  DashboardTile,
  TilePosition,
  TileRunResult,
} from '../types/api';

export const dashboardsApi = {
  list: () => api.get<Dashboard[]>('/dashboards').then((r) => r.data),
  get: (id: string) => api.get<Dashboard>(`/dashboards/${id}`).then((r) => r.data),
  create: (data: Partial<Dashboard>) =>
    api.post<Dashboard>('/dashboards', data).then((r) => r.data),
  update: (id: string, data: Partial<Dashboard>) =>
    api.put<Dashboard>(`/dashboards/${id}`, data).then((r) => r.data),
  delete: (id: string) => api.delete(`/dashboards/${id}`),

  addTile: (
    dashboardId: string,
    data: {
      saved_query_id: string;
      chart_id?: string | null;
      title?: string | null;
      position?: TilePosition;
      refresh_interval?: number | null;
    },
  ) => api.post<DashboardTile>(`/dashboards/${dashboardId}/tiles`, data).then((r) => r.data),
  updateTile: (dashboardId: string, tileId: string, data: Partial<DashboardTile>) =>
    api
      .put<DashboardTile>(`/dashboards/${dashboardId}/tiles/${tileId}`, data)
      .then((r) => r.data),
  deleteTile: (dashboardId: string, tileId: string) =>
    api.delete(`/dashboards/${dashboardId}/tiles/${tileId}`),

  updateLayout: (
    dashboardId: string,
    layout: { tile_id: string; x: number; y: number; w: number; h: number }[],
  ) => api.put<Dashboard>(`/dashboards/${dashboardId}/layout`, { layout }).then((r) => r.data),

  runTile: (
    dashboardId: string,
    tileId: string,
    filters: Record<string, unknown> = {},
    refresh = false,
  ) =>
    api
      .post<TileRunResult>(`/dashboards/${dashboardId}/tiles/${tileId}/run`, { filters, refresh })
      .then((r) => r.data),
};
