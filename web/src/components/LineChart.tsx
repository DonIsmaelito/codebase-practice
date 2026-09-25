import { useMemo, useRef, useState } from "react";

// Single-series trend chart: 2px line, >=8px markers with a surface ring,
// hairline solid grid, crosshair + tooltip, direct label on the latest point.
// Mark hues are validated for the dark surface (see progress page).

export interface Point {
  y: number | null;
  label: string; // company
  sub: string; // date / detail
}

const SURFACE = "#0e1118";
const GRID = "#1d2230";

function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const ticks = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(+v.toFixed(6));
  if (ticks[ticks.length - 1] < max) ticks.push(+(ticks[ticks.length - 1] + step).toFixed(6));
  return ticks;
}

export default function LineChart({
  points,
  color,
  format,
  baseline,
  height = 170,
  yMax,
  emptyText = "Not enough data yet",
}: {
  points: Point[];
  color: string;
  format: (v: number) => string;
  baseline?: { y: number; label: string };
  height?: number;
  yMax?: number;
  emptyText?: string;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const width = 520;
  const pad = { l: 40, r: 56, t: 14, b: 22 };
  const valid = points.map((p, i) => ({ ...p, i })).filter((p) => p.y != null) as (Point & { i: number; y: number })[];

  const { ticks, x, y } = useMemo(() => {
    const max = Math.max(yMax ?? 0, baseline?.y ?? 0, ...valid.map((p) => p.y), 0.0001);
    const ticks = niceTicks(max);
    const top = ticks[ticks.length - 1];
    const n = Math.max(1, points.length - 1);
    return {
      ticks,
      x: (i: number) => pad.l + (points.length === 1 ? (width - pad.l - pad.r) / 2 : (i / n) * (width - pad.l - pad.r)),
      y: (v: number) => pad.t + (1 - v / top) * (height - pad.t - pad.b),
    };
  }, [points.length, valid, baseline, yMax, height]); // eslint-disable-line react-hooks/exhaustive-deps

  if (valid.length < 1) {
    return <div className="grid place-items-center text-[12.5px] text-fg-3" style={{ height }}>{emptyText}</div>;
  }

  const path = valid.map((p, k) => `${k ? "L" : "M"}${x(p.i).toFixed(1)},${y(p.y).toFixed(1)}`).join(" ");
  const last = valid[valid.length - 1];
  const h = hover != null ? valid.find((p) => p.i === hover) : null;

  const onMove = (e: React.PointerEvent) => {
    const svg = ref.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * width;
    let best = valid[0];
    for (const p of valid) if (Math.abs(x(p.i) - px) < Math.abs(x(best.i) - px)) best = p;
    setHover(best.i);
  };

  return (
    <div className="relative">
      <svg
        ref={ref}
        viewBox={`0 0 ${width} ${height}`}
        className="h-auto w-full touch-none"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        role="img"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} stroke={GRID} strokeWidth={1} />
            <text x={pad.l - 8} y={y(t) + 3.5} textAnchor="end" fontSize={10.5} fill="#737c90" style={{ fontVariantNumeric: "tabular-nums" }}>
              {format(t)}
            </text>
          </g>
        ))}
        {baseline && (
          <g>
            <line x1={pad.l} x2={width - pad.r} y1={y(baseline.y)} y2={y(baseline.y)} stroke="#4b5367" strokeWidth={1} />
            <text x={width - pad.r + 6} y={y(baseline.y) + 3.5} fontSize={10.5} fill="#737c90">
              {baseline.label}
            </text>
          </g>
        )}
        {h && <line x1={x(h.i)} x2={x(h.i)} y1={pad.t} y2={height - pad.b} stroke="#4b5367" strokeWidth={1} />}
        <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {valid.map((p) => (
          <circle key={p.i} cx={x(p.i)} cy={y(p.y)} r={hover === p.i ? 5.5 : 4} fill={color} stroke={SURFACE} strokeWidth={2} />
        ))}
        <text x={x(last.i) + 9} y={y(last.y) + 4} fontSize={11.5} fontWeight={600} fill="#e9ecf3">
          {format(last.y)}
        </text>
        {points.map((_, i) =>
          points.length <= 12 || i % Math.ceil(points.length / 10) === 0 ? (
            <text key={i} x={x(i)} y={height - 6} textAnchor="middle" fontSize={10} fill="#4b5367">
              {i + 1}
            </text>
          ) : null,
        )}
      </svg>
      {h && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-lg border border-line-strong bg-ink-2/95 px-2.5 py-1.5 text-[12px] shadow-xl backdrop-blur"
          style={{ left: `${(x(h.i) / width) * 100}%`, top: 0 }}
        >
          <div className="flex items-center gap-1.5">
            <span className="h-0.5 w-3 rounded" style={{ background: color }} />
            <span className="font-semibold text-fg-0">{format(h.y)}</span>
          </div>
          <div className="text-fg-1">{h.label}</div>
          <div className="text-fg-3">{h.sub}</div>
        </div>
      )}
    </div>
  );
}
