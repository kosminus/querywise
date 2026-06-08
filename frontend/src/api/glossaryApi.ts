import { api } from './client';
import type {
  GlossaryTerm,
  LineageRef,
  MetricDefinition,
  DictionaryEntry,
  SemanticVersion,
} from '../types/api';

export const glossaryApi = {
  list: (connectionId: string) =>
    api.get<GlossaryTerm[]>(`/connections/${connectionId}/glossary`).then(r => r.data),
  create: (connectionId: string, data: Partial<GlossaryTerm>) =>
    api.post<GlossaryTerm>(`/connections/${connectionId}/glossary`, data).then(r => r.data),
  update: (connectionId: string, termId: string, data: Partial<GlossaryTerm>) =>
    api.put<GlossaryTerm>(`/connections/${connectionId}/glossary/${termId}`, data).then(r => r.data),
  delete: (connectionId: string, termId: string) =>
    api.delete(`/connections/${connectionId}/glossary/${termId}`),
  transitionStatus: (connectionId: string, termId: string, status: string, reason?: string) =>
    api
      .post<GlossaryTerm>(`/connections/${connectionId}/glossary/${termId}/status`, { status, reason })
      .then(r => r.data),
  versions: (connectionId: string, termId: string) =>
    api
      .get<SemanticVersion[]>(`/connections/${connectionId}/glossary/${termId}/versions`)
      .then(r => r.data),
};

export const metricsApi = {
  list: (connectionId: string) =>
    api.get<MetricDefinition[]>(`/connections/${connectionId}/metrics`).then(r => r.data),
  create: (connectionId: string, data: Partial<MetricDefinition>) =>
    api.post<MetricDefinition>(`/connections/${connectionId}/metrics`, data).then(r => r.data),
  update: (connectionId: string, metricId: string, data: Partial<MetricDefinition>) =>
    api.put<MetricDefinition>(`/connections/${connectionId}/metrics/${metricId}`, data).then(r => r.data),
  delete: (connectionId: string, metricId: string) =>
    api.delete(`/connections/${connectionId}/metrics/${metricId}`),
  transitionStatus: (connectionId: string, metricId: string, status: string, reason?: string) =>
    api
      .post<MetricDefinition>(`/connections/${connectionId}/metrics/${metricId}/status`, { status, reason })
      .then(r => r.data),
  versions: (connectionId: string, metricId: string) =>
    api
      .get<SemanticVersion[]>(`/connections/${connectionId}/metrics/${metricId}/versions`)
      .then(r => r.data),
  lineage: (connectionId: string, metricId: string) =>
    api
      .get<LineageRef[]>(`/connections/${connectionId}/metrics/${metricId}/lineage`)
      .then(r => r.data),
};

export const dictionaryApi = {
  list: (columnId: string) =>
    api.get<DictionaryEntry[]>(`/columns/${columnId}/dictionary`).then(r => r.data),
  create: (columnId: string, data: Partial<DictionaryEntry>) =>
    api.post<DictionaryEntry>(`/columns/${columnId}/dictionary`, data).then(r => r.data),
  update: (columnId: string, entryId: string, data: Partial<DictionaryEntry>) =>
    api.put<DictionaryEntry>(`/columns/${columnId}/dictionary/${entryId}`, data).then(r => r.data),
  delete: (columnId: string, entryId: string) =>
    api.delete(`/columns/${columnId}/dictionary/${entryId}`),
};
