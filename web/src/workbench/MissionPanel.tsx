import clsx from "clsx";
import { AnimatePresence, motion } from "motion/react";
import { Bot, ClipboardList, Clapperboard, Loader2, NotebookText, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { Avatar, Button, Markdown } from "../components/ui";
import { api } from "../lib/api";
import type { EngagementPayload, Nudge, TaskKind } from "../lib/types";
import { muteCoach, useLivePulse } from "./live";
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
  const { rightTab, featurePreparing, unread, nudgeToast } = useWB(
    useShallow((s) => ({ rightTab: s.rightTab, featurePreparing: s.featurePreparing, unread: s.unread, nudgeToast: s.nudgeToast })),
  );
  const set = useWB.getState().set;
  useLivePulse(data);
  const mentorName = data.settings.mentor_name || "Sam";
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
        {tabs.map((t) => {
          const news = t.id !== "notes" && rightTab !== t.id && unread[t.id] > 0;
          return (
            <button
              key={t.id}
              onClick={() => set({ rightTab: t.id, unread: { ...useWB.getState().unread, ...(t.id !== "notes" && { [t.id]: 0 }) }, ...(t.id === "mentor" && { nudgeToast: null }) })}
              className={clsx(
                "relative inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12.5px]",
                rightTab === t.id ? "bg-ink-3 text-fg-0" : "text-fg-2 hover:text-fg-1",
              )}
            >
              {t.icon}
              {t.label}
              {news && <span className={clsx("size-1.5 animate-breathe rounded-full", t.id === "mentor" ? "bg-teal" : "bg-amber")} />}
            </button>
          );
        })}
      </div>
      <div className="relative min-h-0 flex-1">
        <AnimatePresence>
          {nudgeToast && rightTab !== "mentor" && task && <NudgeCard key={nudgeToast.id} nudge={nudgeToast} mentorName={mentorName} taskId={task.id} />}
        </AnimatePresence>
        <div className={clsx("absolute inset-0 overflow-y-auto px-4 py-4", rightTab !== "brief" && "hidden")}>
          {featurePreparing && <FeaturePreparing data={data} />}
          {!featurePreparing && kind === "recon" && <ReconBrief data={data} />}
          {!featurePreparing && kind === "incident" && data.case.incident && <IncidentBrief data={data} onDone={() => onDebrief("incident")} />}
          {!featurePreparing && kind === "feature" && data.case.feature && <FeatureBrief data={data} onDone={() => onDebrief("feature")} />}
          {!featurePreparing && kind && kind !== "recon" && task && ["passed", "revealed", "failed"].includes(task.status) && (
            <Button className="mt-4 w-full" tone={KIND_TONE[kind]} icon={<Sparkles className="size-4" />} onClick={() => onDebrief(kind)}>
              Open the debrief
            </Button>
          )}
          {!featurePreparing && kind === "incident" && task && ["passed", "revealed", "failed"].includes(task.status) && (
            <Button className="mt-2 w-full" ghost icon={<Clapperboard className="size-4" />} onClick={() => set({ replayTask: task.id })}>
              Watch {mentorName} work it
            </Button>
          )}
        </div>
        {task && (
          <div className={clsx("absolute inset-0", rightTab !== "mentor" && "hidden")}>
            <MentorChat key={task.id} taskId={task.id} kind={task.kind} mentorName={mentorName} />
          </div>
        )}
        <div className={clsx("absolute inset-0 p-3", rightTab !== "notes" && "hidden")}>
          <Notes eid={data.engagement.id} initial={data.engagement.notes} />
        </div>
      </div>
    </div>
  );
}

/** The coach checking in after you've been stuck a while: one question, easy to wave off. */
function NudgeCard({ nudge, mentorName, taskId }: { nudge: Nudge; mentorName: string; taskId: string }) {
  const set = useWB.getState().set;
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="absolute inset-x-3 top-3 z-10 rounded-xl border border-teal/30 bg-ink-2 p-3.5 shadow-2xl shadow-black/50"
    >
      <div className="flex items-center gap-2">
        <Avatar name={mentorName} size={22} />
        <span className="text-[12.5px] font-semibold text-fg-0">{mentorName}</span>
        <span className="text-[11.5px] text-teal">checking in</span>
        <button onClick={() => set({ nudgeToast: null })} className="ml-auto rounded p-0.5 text-fg-3 hover:text-fg-0" title="Dismiss">
          <X className="size-3.5" />
        </button>
      </div>
      <Markdown className="mt-2 text-[13px] [&_p]:text-fg-0">{nudge.content}</Markdown>
      <div className="mt-3 flex items-center gap-3">
        <Button size="sm" tone="teal" onClick={() => set({ rightTab: "mentor", nudgeToast: null, unread: { ...useWB.getState().unread, mentor: 0 } })}>
          Answer {mentorName}
        </Button>
        <button
          onClick={() => {
            muteCoach(taskId);
            set({ nudgeToast: null });
          }}
          className="text-[11.5px] text-fg-3 hover:text-fg-1"
        >
          No more check-ins this session
        </button>
      </div>
    </motion.div>
  );
}

function FeaturePreparing({ data }: { data: EngagementPayload }) {
  const [error, setError] = useState<string | null>(null);
  const author = data.case.feature_author || data.case.company.team.find((p) => /product|pm|lead/i.test(p.role))?.name || "Product";
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const r = await api.featureStatus(data.engagement.id);
      if (!alive) return;
      if (r.status === "ready") {
        useWB.getState().set({ featurePreparing: false });
        await useWB.getState().beginTask("feature");
      } else if (r.status === "failed" || r.status === "none") {
        setError(r.error ?? "Something went wrong writing the ticket.");
      }
    };
    const id = window.setInterval(() => void tick(), 4000);
    void tick();
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [data.engagement.id]);
  return (
    <div className="rounded-xl border border-violet/20 bg-violet-dim/30 p-5">
      <div className="flex items-center gap-2 text-[14px] font-medium text-violet">
        <Loader2 className="size-4 animate-spin" /> {author} is writing up the ticket…
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-fg-1">
        It's being specified against this exact codebase and checked by running its tests — usually a minute or two. Poke around the code meanwhile; you'll want to know where things live.
      </p>
      {error && (
        <div className="mt-3 text-[12.5px] text-red">
          {error}{" "}
          <button className="underline" onClick={() => { setError(null); void useWB.getState().takeFeature(); }}>Try again</button>
        </div>
      )}
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
