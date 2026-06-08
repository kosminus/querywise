import { Alert } from '@mantine/core';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import type { ChartType } from '../../types/api';

const PALETTE = [
  '#228be6',
  '#40c057',
  '#fab005',
  '#fa5252',
  '#7950f2',
  '#15aabf',
  '#e64980',
  '#fd7e14',
];

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export interface ChartViewProps {
  columns: string[];
  rows: unknown[][];
  chartType: ChartType;
  xAxis?: string;
  yAxis?: string[];
  height?: number;
}

/** Renders a query result as a Recharts visualization based on chart config. */
export function ChartView({ columns, rows, chartType, xAxis, yAxis, height = 360 }: ChartViewProps) {
  const xKey = xAxis || columns[0];
  const yKeys = (yAxis && yAxis.length > 0 ? yAxis : columns.slice(1)).filter(Boolean);

  if (!xKey || yKeys.length === 0) {
    return <Alert color="yellow">Pick an X axis and at least one Y series to render a chart.</Alert>;
  }

  // Project row arrays into objects keyed by column name; coerce Y values to numbers.
  const data = rows.map((row) => {
    const obj: Record<string, unknown> = {};
    columns.forEach((col, i) => {
      obj[col] = yKeys.includes(col) ? toNumber(row[i]) : row[i];
    });
    return obj;
  });

  if (chartType === 'pie') {
    const valueKey = yKeys[0];
    return (
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Tooltip />
          <Legend />
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey={xKey}
            cx="50%"
            cy="50%"
            outerRadius={120}
            label
          >
            {data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (chartType === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={xKey} name={xKey} />
          <YAxis dataKey={yKeys[0]} name={yKeys[0]} />
          <ZAxis range={[60, 60]} />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} />
          <Legend />
          <Scatter name={yKeys[0]} data={data} fill={PALETTE[0]} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  if (chartType === 'area') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={xKey} />
          <YAxis />
          <Tooltip />
          <Legend />
          {yKeys.map((key, i) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              stroke={PALETTE[i % PALETTE.length]}
              fill={PALETTE[i % PALETTE.length]}
              fillOpacity={0.3}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  if (chartType === 'line') {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={xKey} />
          <YAxis />
          <Tooltip />
          <Legend />
          {yKeys.map((key, i) => (
            <Line key={key} type="monotone" dataKey={key} stroke={PALETTE[i % PALETTE.length]} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  }

  // default: bar
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={xKey} />
        <YAxis />
        <Tooltip />
        <Legend />
        {yKeys.map((key, i) => (
          <Bar key={key} dataKey={key} fill={PALETTE[i % PALETTE.length]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
