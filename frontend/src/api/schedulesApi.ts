import { api } from './client';
import type { Schedule, ScheduleRunResult } from '../types/api';

export const schedulesApi = {
  list: () => api.get<Schedule[]>('/schedules').then((r) => r.data),
  create: (data: Partial<Schedule>) =>
    api.post<Schedule>('/schedules', data).then((r) => r.data),
  update: (id: string, data: Partial<Schedule>) =>
    api.put<Schedule>(`/schedules/${id}`, data).then((r) => r.data),
  remove: (id: string) => api.delete(`/schedules/${id}`).then((r) => r.data),
  run: (id: string) =>
    api.post<ScheduleRunResult>(`/schedules/${id}/run`).then((r) => r.data),
};
