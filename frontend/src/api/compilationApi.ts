import { api } from './client';
import type { CompilationFinding, CompilationRun } from '../types/api';

export interface StartRunOptions {
  llm_enabled?: boolean;
  min_confidence?: number;
  ignore_declared_fks?: boolean;
}

export const compilationApi = {
  startRun: (connectionId: string, options: StartRunOptions = {}) =>
    api
      .post<CompilationRun>(`/connections/${connectionId}/compilation/runs`, options)
      .then(r => r.data),
  listRuns: (connectionId: string) =>
    api.get<CompilationRun[]>(`/connections/${connectionId}/compilation/runs`).then(r => r.data),
  getRun: (connectionId: string, runId: string) =>
    api
      .get<CompilationRun>(`/connections/${connectionId}/compilation/runs/${runId}`)
      .then(r => r.data),
  listFindings: (connectionId: string, params?: { status?: string; kind?: string }) =>
    api
      .get<CompilationFinding[]>(`/connections/${connectionId}/compilation/findings`, { params })
      .then(r => r.data),
  accept: (connectionId: string, findingId: string) =>
    api
      .post<CompilationFinding>(
        `/connections/${connectionId}/compilation/findings/${findingId}/accept`,
      )
      .then(r => r.data),
  dismiss: (connectionId: string, findingId: string) =>
    api
      .post<CompilationFinding>(
        `/connections/${connectionId}/compilation/findings/${findingId}/dismiss`,
      )
      .then(r => r.data),
  bulk: (connectionId: string, findingIds: string[], action: 'accept' | 'dismiss') =>
    api
      .post<{ succeeded: number; failed: number }>(
        `/connections/${connectionId}/compilation/findings/bulk`,
        { finding_ids: findingIds, action },
      )
      .then(r => r.data),
};
