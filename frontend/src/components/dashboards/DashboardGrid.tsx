import { useMemo, useRef } from 'react';
import GridLayout, { type Layout, WidthProvider } from 'react-grid-layout';
import { dashboardsApi } from '../../api/dashboardsApi';
import type { Dashboard } from '../../types/api';
import { DashboardTileCard } from './DashboardTileCard';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

const ResponsiveGrid = WidthProvider(GridLayout);

const DEFAULT_POS = { x: 0, y: Infinity, w: 4, h: 6 };

export function DashboardGrid({
  dashboard,
  filterValues,
  editable,
  onDeleteTile,
}: {
  dashboard: Dashboard;
  filterValues: Record<string, unknown>;
  editable: boolean;
  onDeleteTile: (tileId: string) => void;
}) {
  // Debounce layout persistence so a drag/resize gesture saves once on settle.
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const layout: Layout[] = useMemo(
    () =>
      dashboard.tiles.map((t) => {
        const p = t.position ?? DEFAULT_POS;
        return {
          i: t.id,
          x: p.x ?? 0,
          y: p.y ?? 0,
          w: p.w ?? 4,
          h: p.h ?? 6,
        };
      }),
    [dashboard.tiles],
  );

  const persist = (next: Layout[]) => {
    if (!editable) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      dashboardsApi.updateLayout(
        dashboard.id,
        next.map((l) => ({ tile_id: l.i, x: l.x, y: l.y, w: l.w, h: l.h })),
      );
    }, 600);
  };

  return (
    <ResponsiveGrid
      className="layout"
      layout={layout}
      cols={12}
      rowHeight={30}
      isDraggable={editable}
      isResizable={editable}
      draggableHandle=".tile-drag-handle"
      onDragStop={persist}
      onResizeStop={persist}
    >
      {dashboard.tiles.map((tile) => (
        <div key={tile.id}>
          <DashboardTileCard
            dashboardId={dashboard.id}
            tile={tile}
            filterValues={filterValues}
            editable={editable}
            onDelete={() => onDeleteTile(tile.id)}
          />
        </div>
      ))}
    </ResponsiveGrid>
  );
}
