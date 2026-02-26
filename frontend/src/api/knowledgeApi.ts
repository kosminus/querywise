import { api } from './client';
import type {
  KnowledgeDocument,
  KnowledgeDocumentDetail,
} from '../types/api';

export const knowledgeApi = {
  list: (connectionId: string) =>
    api
      .get<KnowledgeDocument[]>(`/connections/${connectionId}/knowledge`)
      .then((r) => r.data),
  create: (
    connectionId: string,
    data: { title: string; content: string; source_url?: string },
  ) =>
    api
      .post<KnowledgeDocument>(
        `/connections/${connectionId}/knowledge`,
        data,
      )
      .then((r) => r.data),
  get: (connectionId: string, documentId: string) =>
    api
      .get<KnowledgeDocumentDetail>(
        `/connections/${connectionId}/knowledge/${documentId}`,
      )
      .then((r) => r.data),
  delete: (connectionId: string, documentId: string) =>
    api.delete(`/connections/${connectionId}/knowledge/${documentId}`),
  fetchUrl: (url: string) =>
    api
      .post<{ title: string | null; content: string }>(
        '/knowledge/fetch-url',
        { url },
      )
      .then((r) => r.data),
};
