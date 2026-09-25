import clsx from "clsx";
import { Lightbulb } from "lucide-react";
import { useState } from "react";
import { Button, Markdown } from "../../components/ui";
import { api } from "../../lib/api";
import { useWB } from "../store";

const LABELS = ["Nudge", "Where to look", "The exact spot", "What's going wrong"];

export default function Hints({ taskId, seen, total }: { taskId: string; seen: string[]; total: number }) {
  const [hints, setHints] = useState(seen);
  const [loading, setLoading] = useState(false);
  const refresh = useWB((s) => s.refresh);

  const take = async () => {
    setLoading(true);
    try {
      const r = await api.hint(taskId);
      setHints(r.hints);
      void refresh();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-line bg-ink-1">
      <div className="flex items-center gap-2 px-3.5 py-2.5">
        <Lightbulb className="size-3.5 text-amber" />
        <span className="text-[12.5px] font-medium text-fg-1">Hints</span>
        <span className="flex gap-1">
          {Array.from({ length: total }).map((_, i) => (
            <span key={i} className={clsx("h-1 w-4 rounded-full", i < hints.length ? "bg-amber" : "bg-ink-4")} />
          ))}
        </span>
        {hints.length < total && (
          <Button size="sm" ghost className="ml-auto" loading={loading} onClick={() => void take()}>
            {hints.length ? "Next hint" : "I'm stuck"}
          </Button>
        )}
      </div>
      {hints.length > 0 && (
        <div className="space-y-2.5 border-t border-line px-3.5 py-3">
          {hints.map((h, i) => (
            <div key={i}>
              <div className="text-[10.5px] font-semibold tracking-[0.08em] text-amber/80 uppercase">{LABELS[i] ?? `Hint ${i + 1}`}</div>
              <Markdown className="mt-0.5 text-[13px]">{h}</Markdown>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
