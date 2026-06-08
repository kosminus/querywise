import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '../api/analyticsApi';

export function useUsageSummary(days: number, enabled = true) {
  return useQuery({
    queryKey: ['analytics', 'usage', days],
    queryFn: () => analyticsApi.usage(days),
    enabled,
  });
}

export function useCostBy(by: string, days: number, enabled = true) {
  return useQuery({
    queryKey: ['analytics', 'cost', by, days],
    queryFn: () => analyticsApi.cost(by, days),
    enabled,
  });
}

export function useSlowestQueries(days: number, enabled = true) {
  return useQuery({
    queryKey: ['analytics', 'slowest', days],
    queryFn: () => analyticsApi.slowest(days),
    enabled,
  });
}

export function useTableUsage(days: number, enabled = true) {
  return useQuery({
    queryKey: ['analytics', 'tables', days],
    queryFn: () => analyticsApi.tables(days),
    enabled,
  });
}
