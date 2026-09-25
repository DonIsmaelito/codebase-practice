import clsx from "clsx";
import { Bot, ClipboardList, NotebookText, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { Button } from "../components/ui";
import { api } from "../lib/api";
import type { EngagementPayload, TaskKind } from "../lib/types";
import MentorChat from "./mission/MentorChat";
import ReconBrief from "./mission/ReconBrief";
import { FeatureBrief, IncidentBrief } from "./mission/TaskBriefs";
import Timer from "./mission/Timer";
import { useWB } from "./store";

const KIND_TONE = { recon: "blue", incident: "amber", feature: "violet" } as const;
const KIND_LABEL = { recon: "Recon", incident: "Incident", feature: "Ticket" } as const;

export function focusKind(data: EngagementPayload): TaskKind | null {
  const active = Object.values(data.tasks).find((t) => t.status === "active");
  if (active) return active.kind;
  const phase = data.engagement.phase;
  if (phase === "recon" || phase === "incident" || phase === "feature") return phase;
  return null;
}

export default function MissionPanel({ data, viewKind, onDebrief }: { data: EngagementPayload; viewKind: TaskKind | null; onDebrief: (k: TaskKind) => void }) {
  const { rightTab } = useWB(useShallow((s) => ({ rightTab: s.rightTab })));
  const set = useWB.getState().set;
  const kind = viewKind ?? focusKind(data);
  const task = kind ? data.tasks[kind] : null;
  const par =
    kind === "recon" ? data.case.recon.par_minutes : kind === "incident" ? data.case.incident?.par_minutes ?? 15 : data.case.feature?.par_minutes ?? 25;

  const tabs = [
    { id: "brief" as const, label: kind ? KIND_LABEL[kind] : "Brief", icon: <ClipboardList className="size-3.5" /> },
    { id: "mentor" as const, label: data.settings.mentor_name || "Sam", icon: <Bot className="size-3.5" /> },
    { id: "notes" as const, label: "Notes", icon: <NotebookText className="size-3.5" /> },
  ];

  return (
    <div className="flex h-full flex-col bg-ink-1">
      {task && task.status !== "pending" && (
        <div className="border-b border-line px-4 pt-3.5 pb-3">
          <Timer task={task} parMinutes={par} tone={KIND_TONE[task.kind]} countdown={data.settings.timer_mode === "countdown"} />
        </div>
      )}
      <div className="flex h-9 shrink-0 items-center gap-1 border-b border-line px-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => set({ rightTab: t.id })}
            className={clsx(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12.5px]",
              rightTab === t.id ? "bg-ink-3 text-fg-0" : "text-fg-2 hover:text-fg-1",
            )}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>
      <div className="relative min-h-0 flex-1">
        <div className={clsx("absolute inset-0 overflow-y-auto px-4 py-4", rightTab !== "brief" && "hidden")}>
          {kind === "recon" && <ReconBrief data={data} />}
          {kind === "incident" && data.case.incident && <IncidentBrief data={data} onDone={() => onDebrief("incident")} />}
          {kind === "feature" && data.case.feature && <FeatureBrief data={data} onDone={() => onDebrief("feature")} />}
          {kind && kind !== "recon" && task && ["passed", "revealed", "failed"].includes(task.status) && (
            <Button className="mt-4 w-full" tone={KIND_TONE[kind]} icon={<Sparkles className="size-4" />} onClick={() => onDebrief(kind)}>
              Open the debrief
            </Button>
          )}
        </div>
        {task && (
          <div className={clsx("absolute inset-0", rightTab !== "mentor" && "hidden")}>
            <MentorChat key={task.id} taskId={task.id} kind={task.kind} mentorName={data.settings.mentor_name || "Sam"} />
          </div>
        )}
        <div className={clsx("absolute inset-0 p-3", rightTab !== "notes" && "hidden")}>
          <Notes eid={data.engagement.id} initial={data.engagement.notes} />
        </div>
      </div>
    </div>
  );
}

function Notes({ eid, initial }: { eid: string; initial: string }) {
  const [text, setText] = useState(initial);
  const timer = useRef<number>(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <div className="flex h-full flex-col">
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          window.clearTimeout(timer.current);
          const v = e.target.value;
          timer.current = window.setTimeout(() => void api.saveNotes(eid, v), 600);
        }}
        placeholder={"Your scratchpad — offload your working memory.\n\n• entry point:\n• core types:\n• the flow I'm tracing:\n• suspicious:"}
        className="min-h-0 flex-1 resize-none rounded-xl border border-line bg-ink-0 p-3.5 font-mono text-[12.5px] leading-relaxed text-fg-0 outline-none placeholder:text-fg-3 focus:border-line-strong"
      />
    </div>
  );
}

export function Stepper({ data, viewKind, onView }: { data: EngagementPayload; viewKind: TaskKind | null; onView: (k: TaskKind) => void }) {
  const current = viewKind ?? focusKind(data);
  const kinds = (["recon", "incident", "feature"] as TaskKind[]).filter((k) => data.engagement.plan.includes(k) || data.tasks[k].status !== "skipped");
  return (
    <div className="flex items-center gap-1">
      {kinds.map((k, i) => {
        const t = data.tasks[k];
        const done = ["passed", "revealed", "failed"].includes(t.status);
        const active = t.status === "active";
        const clickable = t.status !== "pending" && t.status !== "skipped";
        return (
          <div key={k} className="flex items-center gap-1">
            {i > 0 && <span className="h-px w-5 bg-line-strong" />}
            <button
              disabled={!clickable}
              onClick={() => onView(k)}
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[12px] transition",
                current === k ? "border-line-strong bg-ink-3 text-fg-0" : "border-transparent text-fg-2",
                clickable && current !== k && "hover:text-fg-0",
              )}
            >
              <span
                className={clsx(
                  "size-1.5 rounded-full",
                  done ? (t.status === "passed" ? "bg-green" : "bg-fg-3") : active ? `animate-breathe ${{ recon: "bg-blue", incident: "bg-amber", feature: "bg-violet" }[k]}` : "bg-ink-4",
                )}
              />
              {KIND_LABEL[k]}
            </button>
          </div>
        );
      })}
    </div>
  );
}
