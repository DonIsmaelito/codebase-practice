import clsx from "clsx";
import { useMemo, useState } from "react";
import type { Concept, MasteryState, Region } from "../lib/types";

// Each region is an island; foundational (tier 1) concepts sit at the core,
// advanced ones on the shore. Fog lifts as concepts are actually demonstrated.

export const REGION_COLORS: Record<string, string> = {
  core: "#72b4ff",
  datamodel: "#a98bff",
  stdlib: "#4fd6c8",
  ds: "#56d6a4",
  algo: "#f5b454",
  concurrency: "#f07178",
  data: "#6ec6f0",
  systems: "#f59e6b",
  practice: "#c3e06b",
  ecosystem: "#e38bd8",
};

const STATE_FILL: Record<MasteryState, number> = { fog: 0, glimpsed: 0.16, practiced: 0.42, solid: 0.72, mastered: 1 };

const DIRS: [number, number][] = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];

function spiral(n: number): [number, number][] {
  const out: [number, number][] = [[0, 0]];
  for (let k = 1; out.length < n; k++) {
    let q = DIRS[4][0] * k;
    let r = DIRS[4][1] * k;
    for (let side = 0; side < 6 && out.length < n; side++) {
      for (let step = 0; step < k && out.length < n; step++) {
        out.push([q, r]);
        q += DIRS[side][0];
        r += DIRS[side][1];
      }
    }
  }
  return out;
}

function hexPoints(cx: number, cy: number, size: number): string {
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 180) * (60 * i - 30);
    pts.push(`${(cx + size * Math.cos(a)).toFixed(1)},${(cy + size * Math.sin(a)).toFixed(1)}`);
  }
  return pts.join(" ");
}

interface Placed {
  concept: Concept;
  x: number;
  y: number;
}

export default function HexMap({
  regions,
  concepts,
  onSelect,
  selected,
  mini,
  highlight,
}: {
  regions: Region[];
  concepts: Concept[];
  onSelect?: (c: Concept) => void;
  selected?: string | null;
  mini?: boolean;
  highlight?: Set<string>;
}) {
  const size = mini ? 5.2 : 17;
  const [hover, setHover] = useState<Placed | null>(null);

  const { placed, labels, width, height } = useMemo(() => {
    const w = Math.sqrt(3) * size;
    const h = 1.5 * size;
    const ringsFor = (n: number) => Math.max(1, Math.ceil((Math.sqrt(12 * n - 3) - 3) / 6));
    const maxRings = Math.max(1, ...regions.map((r) => ringsFor(concepts.filter((c) => c.region === r.id).length)));
    // Islands on a staggered 4-3-3 grid, spaced by the biggest island so labels never collide.
    const rowSizes = [4, 3, 3];
    const spacingX = w * (2 * maxRings + 2.6);
    const spacingY = h * (2 * maxRings + 3.4);
    const placed: Placed[] = [];
    const labels: { id: string; name: string; x: number; y: number; color: string }[] = [];
    regions.forEach((region, i) => {
      let row = 0;
      let idx = i;
      while (row < rowSizes.length - 1 && idx >= rowSizes[row]) idx -= rowSizes[row++];
      const rowOffset = ((rowSizes[0] - (rowSizes[row] ?? rowSizes[0])) * spacingX) / 2;
      const cx = w * (maxRings + 1) + idx * spacingX + rowOffset;
      const cy = h * (maxRings + 2.4) + row * spacingY;
      const members = concepts
        .filter((c) => c.region === region.id)
        .sort((a, b) => a.tier - b.tier || a.name.localeCompare(b.name));
      const slots = spiral(members.length);
      members.forEach((concept, j) => {
        const [q, r] = slots[j];
        placed.push({ concept, x: cx + w * (q + r / 2), y: cy + h * r });
      });
      const rings = Math.ceil((Math.sqrt(12 * members.length - 3) - 3) / 6);
      labels.push({ id: region.id, name: region.name, x: cx, y: cy - h * (rings + 1) - size * 0.9, color: REGION_COLORS[region.id] ?? "#aeb6c6" });
    });
    const maxX = Math.max(...placed.map((p) => p.x), 0) + w * 2;
    const maxY = Math.max(...placed.map((p) => p.y), 0) + h * 2;
    return { placed, labels, width: maxX, height: maxY };
  }, [regions, concepts, size]);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label="Concept atlas">
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation={mini ? 1.2 : 3.5} result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {!mini &&
          labels.map((l) => (
            <text key={l.id} x={l.x} y={l.y} textAnchor="middle" fill={l.color} opacity={0.85} fontSize={12.5} fontWeight={600} letterSpacing="0.06em" style={{ textTransform: "uppercase" }}>
              {l.name}
            </text>
          ))}
        {placed.map((p) => {
          const color = REGION_COLORS[p.concept.region] ?? "#aeb6c6";
          const alpha = STATE_FILL[p.concept.state];
          const isSel = selected === p.concept.id;
          const isHi = highlight?.has(p.concept.id);
          return (
            <polygon
              key={p.concept.id}
              className={clsx(!mini && "hex")}
              points={hexPoints(p.x, p.y, size * 0.93)}
              fill={alpha ? color : "#131722"}
              fillOpacity={alpha ? alpha : 1}
              stroke={isSel ? "#e9ecf3" : alpha ? color : "#232a3b"}
              strokeOpacity={isSel ? 1 : alpha ? 0.7 : 1}
              strokeWidth={isSel ? 2 : mini ? 0.6 : 1}
              filter={p.concept.state === "mastered" || isHi ? "url(#glow)" : undefined}
              onMouseEnter={() => !mini && setHover(p)}
              onMouseLeave={() => !mini && setHover(null)}
              onClick={() => onSelect?.(p.concept)}
            />
          );
        })}
      </svg>
      {hover && !mini && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg border border-line-strong bg-ink-2/95 px-2.5 py-1.5 text-[12px] shadow-xl backdrop-blur"
          style={{ left: `${(hover.x / width) * 100}%`, top: `${((hover.y - size) / height) * 100}%` }}
        >
          <div className="font-medium text-fg-0">{hover.concept.name}</div>
          <div className="text-fg-2">
            {hover.concept.state === "fog" ? "Unexplored" : hover.concept.state[0].toUpperCase() + hover.concept.state.slice(1)} · tier {hover.concept.tier}
          </div>
        </div>
      )}
    </div>
  );
}
