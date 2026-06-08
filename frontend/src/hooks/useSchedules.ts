import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { schedulesApi } from '../api/schedulesApi';
import type { Schedule } from '../types/api';

const KEY = ['schedules'];

export function useSchedules() {
  return useQuery({ queryKey: KEY, queryFn: schedulesApi.list });
}

export function useCreateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<Schedule>) => schedulesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Schedule> }) =>
      schedulesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => schedulesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRunSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => schedulesApi.run(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
