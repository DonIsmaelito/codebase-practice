import { useMemo } from "react";

// A quiet record of the days you showed up. Not a streak counter.

function levelFor(minutes: number): number {
  if (minutes <= 0) return 0;
  if (minutes < 10) return 1;
  if (minutes < 25) return 2;
  if (minutes < 50) return 3;
  return 4;
}

const FILLS = ["#131722", "#1d3b5c", "#2a5b8f", "#4687cf", "#72b4ff"];

export default function Heatmap({ days, weeks = 26 }: { days: { day: string; seconds: number }[]; weeks?: number }) {
  const cells = useMemo(() => {
    const byDay = new Map(days.map((d) => [d.day, d.seconds]));
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const start = new Date(today);
    start.setDate(start.getDate() - (weeks * 7 - 1) - today.getDay());
    const out: { day: string; minutes: number; col: number; row: number; future: boolean }[] = [];
    for (let i = 0; i < weeks * 7 + today.getDay() + 1; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      out.push({ day: key, minutes: Math.round((byDay.get(key) ?? 0) / 60), col: Math.floor(i / 7), row: d.getDay(), future: d > today });
    }
    return out;
  }, [days, weeks]);

  const cols = Math.max(...cells.map((c) => c.col)) + 1;
  const cell = 11;
  const gap = 3;
  return (
    <svg viewBox={`0 0 ${cols * (cell + gap)} ${7 * (cell + gap)}`} className="h-auto w-full">
      {cells.map((c) =>
        c.future ? null : (
          <rect key={c.day} x={c.col * (cell + gap)} y={c.row * (cell + gap)} width={cell} height={cell} rx={2.5} fill={FILLS[levelFor(c.minutes)]}>
            <title>{`${c.day}: ${c.minutes ? `${c.minutes} min` : "no practice"}`}</title>
          </rect>
        ),
      )}
    </svg>
  );
}
