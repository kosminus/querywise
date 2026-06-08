import { api } from './client';
import type {
  Chart,
  ChartType,
  ChartConfig,
  SavedQuery,
  SavedQueryRunResult,
} from '../types/api';

const base = (connectionId: string) => `/connections/${connectionId}/saved-queries`;

export const savedQueriesApi = {
  list: (connectionId: string) =>
    api.get<SavedQuery[]>(base(connectionId)).then((r) => r.data),
  get: (connectionId: string, id: string) =>
    api.get<SavedQuery>(`${base(connectionId)}/${id}`).then((r) => r.data),
  create: (connectionId: string, data: Partial<SavedQuery>) =>
    api.post<SavedQuery>(base(connectionId), data).then((r) => r.data),
  update: (connectionId: string, id: string, data: Partial<SavedQuery>) =>
    api.put<SavedQuery>(`${base(connectionId)}/${id}`, data).then((r) => r.data),
  delete: (connectionId: string, id: string) =>
    api.delete(`${base(connectionId)}/${id}`),
  clone: (connectionId: string, id: string) =>
    api.post<SavedQuery>(`${base(connectionId)}/${id}/clone`).then((r) => r.data),
  run: (
    connectionId: string,
    id: string,
    params: Record<string, unknown> = {},
    refresh = false,
  ) =>
    api
      .post<SavedQueryRunResult>(`${base(connectionId)}/${id}/run`, { params, refresh })
      .then((r) => r.data),
  exportUrl: (connectionId: string, id: string, format: 'csv' | 'json' | 'xlsx') =>
    `${api.defaults.baseURL}${base(connectionId)}/${id}/export?format=${format}`,
};

export const chartsApi = {
  list: (connectionId: string, savedQueryId: string) =>
    api
      .get<Chart[]>(`${base(connectionId)}/${savedQueryId}/charts`)
      .then((r) => r.data),
  create: (
    connectionId: string,
    savedQueryId: string,
    data: { name: string; chart_type: ChartType; config: ChartConfig },
  ) =>
    api
      .post<Chart>(`${base(connectionId)}/${savedQueryId}/charts`, data)
      .then((r) => r.data),
  update: (
    connectionId: string,
    savedQueryId: string,
    chartId: string,
    data: Partial<{ name: string; chart_type: ChartType; config: ChartConfig }>,
  ) =>
    api
      .put<Chart>(`${base(connectionId)}/${savedQueryId}/charts/${chartId}`, data)
      .then((r) => r.data),
  delete: (connectionId: string, savedQueryId: string, chartId: string) =>
    api.delete(`${base(connectionId)}/${savedQueryId}/charts/${chartId}`),
};
