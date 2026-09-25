import clsx from "clsx";
import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../../lib/api";
import { clock } from "../../lib/format";
import type { Task } from "../../lib/types";

// Counts only active, un-paused, visible time. Heartbeats go to the server so
// the debrief and your progress charts use the same honest number.
export default function Timer({ task, parMinutes, tone, countdown }: { task: Task; parMinutes: number; tone: "blue" | "amber" | "violet"; countdown?: boolean }) {
  const [seconds, setSeconds] = useState(task.active_seconds);
  const [paused, setPaused] = useState(false);
  const pending = useRef(0);
  const running = task.status === "active" && !paused;

  useEffect(() => {
    setSeconds(task.active_seconds);
    pending.current = 0;
  }, [task.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!running) return;
    const tickId = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      setSeconds((s) => s + 1);
      pending.current += 1;
    }, 1000);
    const flushId = window.setInterval(() => {
      if (pending.current > 0) {
        const n = pending.current;
        pending.current = 0;
        void api.tick(task.id, n).catch(() => (pending.current += n));
      }
    }, 15000);
    return () => {
      window.clearInterval(tickId);
      window.clearInterval(flushId);
      if (pending.current > 0) {
        void api.tick(task.id, pending.current).catch(() => {});
        pending.current = 0;
      }
    };
  }, [running, task.id]);

  const par = parMinutes * 60;
  const ratio = par ? seconds / par : 0;
  const over = seconds > par;
  const display = countdown ? (over ? `+${clock(seconds - par)}` : clock(par - seconds)) : clock(seconds);
  const barColor = over ? "bg-amber" : { blue: "bg-blue", amber: "bg-amber", violet: "bg-violet" }[tone];

  return (
    <div className="flex items-center gap-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className={clsx("font-mono text-[26px] leading-none tracking-tight tabular-nums", paused ? "text-fg-3" : "text-fg-0")}>{display}</span>
          <span className="text-[11.5px] text-fg-2">par {parMinutes}m</span>
          {paused && <span className="text-[11px] font-medium text-amber">paused</span>}
        </div>
        <div className="mt-2 h-[3px] overflow-hidden rounded-full bg-ink-3">
          <div className={clsx("h-full rounded-full transition-[width] duration-1000", barColor, over && "animate-breathe")} style={{ width: `${Math.min(1, ratio) * 100}%` }} />
        </div>
      </div>
      {task.status === "active" && (
        <button
          onClick={() => setPaused((p) => !p)}
          className="grid size-8 place-items-center rounded-lg border border-line-strong text-fg-1 hover:bg-ink-3 hover:text-fg-0"
          title={paused ? "Resume" : "Pause"}
        >
          {paused ? <Play className="size-3.5" /> : <Pause className="size-3.5" />}
        </button>
      )}
    </div>
  );
}
