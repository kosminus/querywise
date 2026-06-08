import { api } from './client';
import type { DataPolicy } from '../types/api';

const base = (connectionId: string) => `/connections/${connectionId}/policies`;

export const policiesApi = {
  list: (connectionId: string) =>
    api.get<DataPolicy[]>(base(connectionId)).then((r) => r.data),
  create: (connectionId: string, data: Partial<DataPolicy>) =>
    api.post<DataPolicy>(base(connectionId), data).then((r) => r.data),
  update: (connectionId: string, id: string, data: Partial<DataPolicy>) =>
    api.put<DataPolicy>(`${base(connectionId)}/${id}`, data).then((r) => r.data),
  remove: (connectionId: string, id: string) =>
    api.delete(`${base(connectionId)}/${id}`).then((r) => r.data),
};
