import { useQuery } from '@tanstack/react-query';
import { catalogApi, type CatalogSearchParams } from '../api/catalogApi';

export function useCatalogSearch(
  connectionId: string | undefined,
  params: CatalogSearchParams,
) {
  return useQuery({
    queryKey: ['catalog', 'search', connectionId, params],
    queryFn: () => catalogApi.search(connectionId!, params),
    enabled: !!connectionId,
  });
}

export function useCatalogFacets(connectionId: string | undefined) {
  return useQuery({
    queryKey: ['catalog', 'facets', connectionId],
    queryFn: () => catalogApi.facets(connectionId!),
    enabled: !!connectionId,
  });
}

export function useCatalogLineage(
  connectionId: string | undefined,
  table: string | undefined,
  column?: string,
) {
  return useQuery({
    queryKey: ['catalog', 'lineage', connectionId, table, column],
    queryFn: () => catalogApi.lineageImpact(connectionId!, table!, column),
    enabled: !!connectionId && !!table,
  });
}
