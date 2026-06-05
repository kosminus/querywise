import { api } from './client';
import type { AssistantResponse } from '../types/api';

export const assistantApi = {
  send: (data: {
    connection_id: string;
    message: string;
    history: { role: 'user' | 'assistant'; content: string }[];
  }) => api.post<AssistantResponse>('/query/assistant', data).then((r) => r.data),
};
