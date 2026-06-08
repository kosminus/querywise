import { api } from './client';
import type { CostByEntry, SlowestQuery, TableUsage, UsageSummary } from '../types/api';

export const analyticsApi = {
  usage: (days: number) =>
    api.get<UsageSummary>('/analytics/usage', { params: { days } }).then((r) => r.data),
  cost: (by: string, days: number) =>
    api.get<CostByEntry[]>('/analytics/cost', { params: { by, days } }).then((r) => r.data),
  slowest: (days: number, limit = 10) =>
    api
      .get<SlowestQuery[]>('/analytics/slowest', { params: { days, limit } })
      .then((r) => r.data),
  tables: (days: number, limit = 10) =>
    api.get<TableUsage[]>('/analytics/tables', { params: { days, limit } }).then((r) => r.data),
};
