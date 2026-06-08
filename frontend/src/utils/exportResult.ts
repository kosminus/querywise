// Client-side export helpers for tabular query results (columns + row arrays).
// Used for ad-hoc Query results and saved-query runs without a backend round-trip.

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  // Quote if the cell contains a comma, quote, or newline; double embedded quotes.
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function downloadCsv(columns: string[], rows: unknown[][], baseName: string) {
  const header = columns.map(csvCell).join(',');
  const body = rows.map((row) => row.map(csvCell).join(',')).join('\n');
  const csv = `${header}\n${body}`;
  triggerDownload(new Blob([csv], { type: 'text/csv' }), `${sanitize(baseName)}.csv`);
}

export function downloadJson(columns: string[], rows: unknown[][], baseName: string) {
  const objects = rows.map((row) =>
    Object.fromEntries(columns.map((col, i) => [col, row[i] ?? null])),
  );
  triggerDownload(
    new Blob([JSON.stringify(objects, null, 2)], { type: 'application/json' }),
    `${sanitize(baseName)}.json`,
  );
}

function sanitize(name: string): string {
  return name.trim().replace(/\s+/g, '_').replace(/[^\w-]/g, '') || 'result';
}
