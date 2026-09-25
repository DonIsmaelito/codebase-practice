import { useEffect, useMemo, useState } from "react";
import Heatmap from "../components/Heatmap";
import LineChart, { type Point } from "../components/LineChart";
import { Card, Chip, EmptyState, SectionLabel, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { duration } from "../lib/format";
import type { ProgressRow } from "../lib/types";

// Chart mark hues, validated against the dark chart surface (#0e1118):
// all pass lightness band, chroma, CVD and contrast checks.
const MARK = { recon: "#4f95e8", incident: "#c4862a", size: "#2aa396" };

const outcomeTone = { clean: "green", assisted: "blue", revealed: "neutral", failed: "red" } as const;

function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card className="p-4">
      <div className="text-[12px] text-fg-2">{label}</div>
      <div className="mt-1 text-[28px] leading-tight font-semibold text-fg-0">{value}</div>
      {note && <div className="mt-0.5 text-[12px] text-fg-2">{note}</div>}
    </Card>
  );
}

export default function Progress() {
  const [data, setData] = useState<{ engagements: ProgressRow[]; calendar: { day: string; seconds: number }[] } | null>(null);
  useEffect(() => {
    api.progress().then(setData);
  }, []);

  const rows = useMemo(() => (data?.engagements ?? []).filter((r) => r.incident || r.recon_accuracy != null || r.feature), [data]);
  const pts = (f: (r: ProgressRow) => number | null): Point[] =>
    rows.map((r) => ({ y: f(r), label: r.company, sub: `${new Date(r.when * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" })} · ${r.loc.toLocaleString()} lines` }));

  if (!data) return <div className="grid h-[60vh] place-items-center"><Spinner className="size-6" /></div>;

  const rootTimes = rows.map((r) => r.incident?.time_to_root_file).filter((v): v is number => v != null);
  const firstFive = median(rootTimes.slice(0, 5));
  const lastFive = median(rootTimes.slice(-5));
  const totalSeconds = data.calendar.reduce((s, d) => s + d.seconds, 0);
  const sizes = rows.map((r) => r.loc);

  return (
    <div className="mx-auto max-w-[1180px] px-6 py-10">
      <h1 className="font-serif text-[42px] leading-none text-fg-0">Progress</h1>
      <p className="mt-2 text-[14.5px] text-fg-1">No scores. Just your real numbers, engagement by engagement.</p>

      {rows.length === 0 ? (
        <Card className="mt-8">
          <EmptyState title="Nothing to chart yet">Finish your first engagement and your trends start here: how fast you find the root cause, how long fixes take against par, and how big the codebases you handle get.</EmptyState>
        </Card>
      ) : (
        <>
          <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Engagements" value={String(rows.length)} note={`${duration(totalSeconds)} of focused practice`} />
            <Stat
              label="Time to the root-cause file"
              value={lastFive != null ? duration(lastFive) : "—"}
              note={firstFive != null && lastFive != null && rootTimes.length > 5 ? `median of last 5 · first 5 were ${duration(firstFive)}` : "median of recent engagements"}
            />
            <Stat label="Codebase size now" value={`${(sizes[sizes.length - 1] ?? 0).toLocaleString()} lines`} note={sizes.length > 1 ? `started at ${sizes[0].toLocaleString()}` : undefined} />
            <Stat
              label="Recon accuracy (recent)"
              value={(() => {
                const acc = rows.map((r) => r.recon_accuracy).filter((v): v is number => v != null).slice(-5);
                return acc.length ? `${Math.round((acc.reduce((a, b) => a + b, 0) / acc.length) * 100)}%` : "—";
              })()}
              note="how well your mental model held up"
            />
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <Card className="p-5">
              <SectionLabel>Minutes until you opened the root-cause file</SectionLabel>
              <p className="mt-1 text-[12.5px] text-fg-2">The core skill: getting from a report to the right place, fast.</p>
              <div className="mt-3">
                <LineChart points={pts((r) => (r.incident?.time_to_root_file != null ? r.incident.time_to_root_file / 60 : null))} color={MARK.incident} format={(v) => `${v.toFixed(v < 10 ? 1 : 0)}m`} />
              </div>
            </Card>
            <Card className="p-5">
              <SectionLabel>Incident time, relative to par</SectionLabel>
              <p className="mt-1 text-[12.5px] text-fg-2">1.0× is par for that codebase's difficulty. Below the line is faster.</p>
              <div className="mt-3">
                <LineChart
                  points={pts((r) => (r.incident && r.incident.par_seconds ? r.incident.seconds / r.incident.par_seconds : null))}
                  color={MARK.incident}
                  format={(v) => `${v.toFixed(1)}×`}
                  baseline={{ y: 1, label: "par" }}
                />
              </div>
            </Card>
            <Card className="p-5">
              <SectionLabel>Recon accuracy</SectionLabel>
              <p className="mt-1 text-[12.5px] text-fg-2">How well your map of each codebase matched reality.</p>
              <div className="mt-3">
                <LineChart points={pts((r) => r.recon_accuracy)} color={MARK.recon} format={(v) => `${Math.round(v * 100)}%`} yMax={1} />
              </div>
            </Card>
            <Card className="p-5">
              <SectionLabel>Size of the codebases you're handling</SectionLabel>
              <p className="mt-1 text-[12.5px] text-fg-2">Non-test lines of code. This grows as you do.</p>
              <div className="mt-3">
                <LineChart points={pts((r) => r.loc)} color={MARK.size} format={(v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : `${Math.round(v)}`)} />
              </div>
            </Card>
          </div>
        </>
      )}

      <Card className="mt-6 p-5">
        <SectionLabel>Days you practiced</SectionLabel>
        <div className="mt-4">
          <Heatmap days={data.calendar} weeks={52} />
        </div>
      </Card>

      {rows.length > 0 && (
        <Card className="mt-6 overflow-hidden">
          <table className="w-full text-left text-[12.5px]">
            <thead className="border-b border-line bg-ink-2 text-fg-2">
              <tr>
                {["#", "Client", "Size", "Recon", "Incident", "Root file", "Ticket"].map((h) => (
                  <th key={h} className="px-4 py-2.5 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-2.5 text-fg-3 tabular-nums">{i + 1}</td>
                  <td className="px-4 py-2.5">
                    <div className="text-fg-0">{r.company}</div>
                    <div className="text-[11.5px] text-fg-3">{r.domain}</div>
                  </td>
                  <td className="px-4 py-2.5 text-fg-1 tabular-nums">{r.loc.toLocaleString()}</td>
                  <td className="px-4 py-2.5 text-fg-1 tabular-nums">{r.recon_accuracy != null ? `${Math.round(r.recon_accuracy * 100)}%` : "—"}</td>
                  <td className="px-4 py-2.5">
                    {r.incident ? (
                      <span className="flex items-center gap-2">
                        <Chip tone={outcomeTone[r.incident.outcome]}>{r.incident.outcome}</Chip>
                        <span className="text-fg-1 tabular-nums">{duration(r.incident.seconds)}</span>
                      </span>
                    ) : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-fg-1 tabular-nums">{r.incident?.time_to_root_file != null ? duration(r.incident.time_to_root_file) : "—"}</td>
                  <td className="px-4 py-2.5">
                    {r.feature ? (
                      <span className="flex items-center gap-2">
                        <Chip tone={outcomeTone[r.feature.outcome]}>{r.feature.outcome}</Chip>
                        <span className="text-fg-1 tabular-nums">{duration(r.feature.seconds)}</span>
                      </span>
                    ) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
