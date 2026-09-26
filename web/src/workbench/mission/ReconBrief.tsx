import clsx from "clsx";
import { motion } from "motion/react";
import { ArrowRight, Check, CircleDot, Compass, EyeOff, MapPin, Route } from "lucide-react";
import { useEffect, useState } from "react";
import { Avatar, Button, Chip, Markdown, SectionLabel } from "../../components/ui";
import { api } from "../../lib/api";
import { clock } from "../../lib/format";
import type { EngagementPayload, ReconResult, TaskResult } from "../../lib/types";
import { useWB } from "../store";

const verdictTone = { correct: "green", partial: "amber", incorrect: "red" } as const;

export default function ReconBrief({ data }: { data: EngagementPayload }) {
  const recon = data.case.recon;
  const task = data.tasks.recon;
  const { openFile, set, beginTask, takeFeature, refresh } = useWB.getState();
  const [visited, setVisited] = useState<Set<number>>(new Set());
  const [showTour, setShowTour] = useState(recon.mode === "guided");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [grading, setGrading] = useState(false);
  const [phase, setPhase] = useState<"explore" | "answer">(recon.mode === "closed" ? "explore" : "answer");
  const [scoutLeft, setScoutLeft] = useState(recon.par_minutes * 60);
  const result = (task.result as (TaskResult & ReconResult) | null) ?? null;
  const done = task.status !== "active" && task.status !== "pending";

  // Closed-book: a scouting countdown, then the code hides while answering.
  useEffect(() => {
    if (recon.mode !== "closed" || phase !== "explore" || done) return;
    const id = window.setInterval(() => setScoutLeft((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearInterval(id);
  }, [recon.mode, phase, done]);

  useEffect(() => {
    set({ codeHidden: recon.mode === "closed" && phase === "answer" && !done });
    return () => set({ codeHidden: false });
  }, [recon.mode, phase, done, set]);

  const visit = (i: number) => {
    const stop = recon.tour[i];
    const next = new Set(visited);
    next.add(i);
    setVisited(next);
    const end = stop.line + 5;
    void openFile(stop.path, false, stop.line, 1, "tour", end);
  };

  const submit = async () => {
    setGrading(true);
    try {
      await api.recon(task.id, answers);
      await refresh();
    } finally {
      setGrading(false);
    }
  };

  const next = data.engagement.plan.find((k) => k !== "recon" && data.tasks[k].status === "pending");

  return (
    <div className="space-y-5">
      <div className="flex gap-2.5">
        <Avatar name={recon.briefing.from} size={30} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="text-[13px] font-semibold text-fg-0">{recon.briefing.from}</span>
            {recon.briefing.role && <span className="text-[11.5px] text-fg-2">{recon.briefing.role}</span>}
          </div>
          <div className="mt-1 rounded-xl rounded-tl-sm border border-line bg-ink-2/60 px-3.5 py-3">
            <Markdown className="text-[13px]">{recon.briefing.body}</Markdown>
          </div>
        </div>
      </div>

      {recon.mode === "closed" && !done && phase === "explore" && (
        <div className="rounded-xl border border-blue/25 bg-blue-dim/40 p-4">
          <div className="flex items-center gap-2 text-[13px] font-medium text-blue">
            <Compass className="size-4" /> Scouting — {clock(scoutLeft)} left
          </div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-fg-1">
            Build a mental map: entry points, the core data types, how one request flows through. When you're ready (or time's up), the code hides and you answer from memory.
          </p>
          <Button className="mt-3" size="sm" tone="blue" onClick={() => setPhase("answer")}>
            {scoutLeft === 0 ? "Time's up — answer now" : "I'm ready to answer"}
          </Button>
        </div>
      )}

      {recon.tour.length > 0 && (recon.mode !== "closed" || done) && (
        <div>
          <div className="flex items-center justify-between">
            <SectionLabel className="flex items-center gap-1.5">
              <Route className="size-3.5" /> Guided tour
            </SectionLabel>
            {!showTour && (
              <Button size="sm" ghost onClick={() => setShowTour(true)}>
                Show me around
              </Button>
            )}
          </div>
          {showTour && (
            <ol className="mt-2 space-y-1">
              {recon.tour.map((stop, i) => (
                <li key={i}>
                  <button onClick={() => visit(i)} className="group flex w-full gap-3 rounded-lg px-2 py-2 text-left hover:bg-ink-3">
                    <span
                      className={clsx(
                        "mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border text-[10.5px] font-semibold",
                        visited.has(i) ? "border-blue bg-blue text-ink-0" : "border-line-strong text-fg-2",
                      )}
                    >
                      {visited.has(i) ? <Check className="size-3" strokeWidth={3} /> : i + 1}
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[13px] font-medium text-fg-0">{stop.title}</span>
                      <span className="block truncate font-mono text-[11px] text-fg-3">
                        {stop.path}:{stop.line}
                      </span>
                      {visited.has(i) && <Markdown className="mt-1 text-[12.5px]">{stop.note}</Markdown>}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {(phase === "answer" || done) && (
        <div>
          <SectionLabel className="flex items-center gap-1.5">
            {recon.mode === "closed" && !done ? <EyeOff className="size-3.5" /> : <MapPin className="size-3.5" />}
            {recon.mode === "closed" && !done ? "From memory" : "Check your understanding"}
          </SectionLabel>
          <div className="mt-3 space-y-4">
            {recon.questions.map((q, i) => {
              const r = result?.results?.find((x) => x.id === q.id);
              return (
                <div key={q.id}>
                  <div className="flex gap-2">
                    <span className="mt-0.5 font-mono text-[11px] text-fg-3">{i + 1}.</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Chip tone="blue">{q.kind}</Chip>
                        {r && <Chip tone={verdictTone[r.verdict]}>{r.verdict}</Chip>}
                      </div>
                      <Markdown className="mt-1.5 text-[13px]">{q.prompt}</Markdown>
                      {done ? (
                        <div className="mt-2 space-y-1.5 text-[12.5px]">
                          <div className="rounded-lg border border-line bg-ink-2/50 px-3 py-2 text-fg-1">
                            <span className="text-fg-3">You: </span>
                            {r?.given || <span className="italic text-fg-3">no answer</span>}
                          </div>
                          {r?.feedback && <Markdown className="text-[12.5px]">{r.feedback}</Markdown>}
                          <div className="rounded-lg border border-green/15 bg-green-dim/30 px-3 py-2">
                            <span className="text-green">Answer: </span>
                            <span className="font-mono text-[12px] text-fg-0">{r?.answer}</span>
                          </div>
                        </div>
                      ) : (
                        <textarea
                          value={answers[q.id] ?? ""}
                          onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                          rows={q.kind === "predict" ? 1 : 3}
                          placeholder={q.kind === "predict" ? "exact value, e.g. Decimal('3.50')" : q.kind === "locate" ? "file and function" : "your answer"}
                          className={clsx(
                            "mt-2 w-full resize-y rounded-lg border border-line-strong bg-ink-0 px-3 py-2 text-[13px] text-fg-0 outline-none placeholder:text-fg-3 focus:border-blue",
                            q.kind === "predict" && "font-mono",
                          )}
                        />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {!done && (
            <Button className="mt-4 w-full" tone="blue" loading={grading} onClick={() => void submit()}>
              {grading ? "Checking your answers…" : "Submit answers"}
            </Button>
          )}
        </div>
      )}

      {done && result && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          {result.overall && (
            <div className="rounded-xl border border-blue/20 bg-blue-dim/30 p-3.5">
              <Markdown className="text-[13px]">{result.overall}</Markdown>
            </div>
          )}
          {result.map && <MapView map={result.map} />}
          {next && (
            <Button className="w-full" tone={next === "incident" ? "amber" : "violet"} icon={<ArrowRight className="size-4" />} onClick={() => void (next === "feature" ? takeFeature() : beginTask(next))}>
              {next === "incident" ? "Something just came in…" : "Pick up the feature ticket"}
            </Button>
          )}
        </motion.div>
      )}
    </div>
  );
}

function MapView({ map }: { map: NonNullable<ReconResult["map"]> }) {
  const openFile = useWB.getState().openFile;
  return (
    <div className="rounded-xl border border-line bg-ink-1 p-4">
      <SectionLabel>How an expert sees this codebase</SectionLabel>
      <Markdown className="mt-2 text-[13px]">{map.summary}</Markdown>
      <div className="mt-3 space-y-2">
        {map.components.map((c) => (
          <div key={c.name} className="text-[12.5px]">
            <span className="font-medium text-fg-0">{c.name}</span> <span className="text-fg-2">— {c.role}</span>
            <div className="mt-0.5 flex flex-wrap gap-1">
              {c.paths.map((p) => (
                <button key={p} onClick={() => void openFile(p)} className="font-mono text-[11px] text-blue hover:underline">
                  {p}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {map.flows.map((f) => (
        <div key={f.name} className="mt-3">
          <div className="text-[12px] font-medium text-fg-1">{f.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1 font-mono text-[11px] text-fg-2">
            {f.steps.map((s, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <CircleDot className="size-2 text-fg-3" />}
                <span className="rounded bg-ink-3 px-1.5 py-0.5 text-fg-1">{s}</span>
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
