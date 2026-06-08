import { api } from './client';
import type { CatalogFacets, CatalogHit, LineageRef } from '../types/api';

export interface CatalogSearchParams {
  q?: string;
  types?: string[];
  status?: string;
  owner?: string;
  schema?: string;
  limit?: number;
}

export const catalogApi = {
  search: (connectionId: string, params: CatalogSearchParams) =>
    api
      .get<CatalogHit[]>(`/connections/${connectionId}/catalog/search`, {
        params: {
          q: params.q ?? '',
          types: params.types?.length ? params.types.join(',') : undefined,
          status: params.status || undefined,
          owner: params.owner || undefined,
          schema: params.schema || undefined,
          limit: params.limit ?? 50,
        },
      })
      .then((r) => r.data),
  facets: (connectionId: string) =>
    api.get<CatalogFacets>(`/connections/${connectionId}/catalog/facets`).then((r) => r.data),
  lineageImpact: (connectionId: string, table: string, column?: string) =>
    api
      .get<LineageRef[]>(`/connections/${connectionId}/catalog/lineage`, {
        params: { table, column: column || undefined },
      })
      .then((r) => r.data),
};
