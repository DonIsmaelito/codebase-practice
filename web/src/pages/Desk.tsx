import clsx from "clsx";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, BookOpen, Bug, FileText, Hash, Mail, Map as MapIcon, Radio, RefreshCw, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import Heatmap from "../components/Heatmap";
import HexMap from "../components/HexMap";
import { Button, Card, Chip, Markdown, Monogram, SectionLabel, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useDesk } from "../lib/desk";
import { ago, duration, fidelityLabel, greeting } from "../lib/format";
import { usePageTitle } from "../lib/title";
import type { CaseCard, Concept, PipelineItem, RecallCard, Region } from "../lib/types";

const channelIcon: Record<string, typeof Mail> = { slack: Hash, email: Mail, jira: FileText, pager: Radio };

export default function Desk() {
  usePageTitle("Desk");
  const { state, load, error } = useDesk();
  const [atlas, setAtlas] = useState<{ regions: Region[]; concepts: Concept[] } | null>(null);

  useEffect(() => {
    void load();
    api.atlas().then(setAtlas).catch(() => {});
  }, [load]);

  const busy = (state?.pipeline.length ?? 0) > 0;
  useEffect(() => {
    const id = window.setInterval(() => void load(), busy ? 3000 : 15000);
    return () => window.clearInterval(id);
  }, [busy, load]);

  const weekMinutes = useMemo(() => {
    if (!state) return 0;
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - 6);
    const key = cutoff.toISOString().slice(0, 10);
    return Math.round(state.calendar.filter((d) => d.day >= key).reduce((s, d) => s + d.seconds, 0) / 60);
  }, [state]);

  if (!state) {
    return (
      <div className="grid h-[60vh] place-items-center">
        {error ? <div className="text-red">Can't reach the server: {error}</div> : <Spinner className="size-6" />}
      </div>
    );
  }

  const uncovered = atlas?.concepts.filter((c) => c.state !== "fog").length ?? 0;

  return (
    <div className="mx-auto grid max-w-[1280px] grid-cols-1 gap-8 px-6 py-10 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0">
        <div className="animate-rise">
          <h1 className="font-serif text-[44px] leading-[1.05] tracking-tight text-fg-0">{greeting()}.</h1>
          <p className="mt-2 text-[15px] text-fg-1">
            {state.inbox.length
              ? `${state.inbox.length === 1 ? "One client needs" : `${state.inbox.length} clients need`} a contractor. Pick one — every codebase is new territory.`
              : busy
                ? "New clients are getting in touch. They'll land in your inbox in a few minutes."
                : "Your inbox is empty."}
          </p>
        </div>

        {state.first_run && <FirstRun />}

        {state.active && (
          <Link
            to={`/e/${state.active.id}`}
            className="mt-8 flex items-center gap-4 rounded-2xl border border-amber/25 bg-gradient-to-r from-amber-dim to-ink-1 p-5 transition hover:border-amber/50"
          >
            <span className="size-2 animate-breathe rounded-full bg-amber" />
            <div className="min-w-0 flex-1">
              <div className="text-[12px] font-medium tracking-wide text-amber uppercase">Engagement in progress · {state.active.phase}</div>
              <div className="truncate text-[16px] text-fg-0">{state.active.company} — {state.active.subject}</div>
            </div>
            <ArrowRight className="size-5 text-amber" />
          </Link>
        )}

        <div className="mt-10 flex items-center justify-between">
          <SectionLabel>Inbox</SectionLabel>
          <Button size="sm" ghost icon={<RefreshCw className="size-3.5" />} onClick={() => void api.generate().then(() => load())}>
            Request another client
          </Button>
        </div>
        <div className="mt-3 space-y-3">
          <AnimatePresence initial={false}>
            {state.inbox.map((c, i) => (
              <motion.div key={c.id} layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0, transition: { delay: i * 0.06 } }} exit={{ opacity: 0, x: -30 }}>
                <InboxCard card={c} disabled={!!state.active} onDismiss={() => void api.dismiss(c.id).then(() => load())} />
              </motion.div>
            ))}
          </AnimatePresence>
          {!state.inbox.length && !busy && (
            <Card className="p-8 text-center">
              <div className="text-fg-1">No clients waiting.</div>
              <Button className="mt-4" tone="blue" icon={<Sparkles className="size-4" />} onClick={() => void api.generate().then(() => load())}>
                Find me a client
              </Button>
            </Card>
          )}
        </div>

        {state.pipeline.length > 0 && (
          <div className="mt-8">
            <SectionLabel>On the way</SectionLabel>
            <div className="mt-3 space-y-2">
              {state.pipeline.map((p) => (
                <PipelineRow key={p.id} item={p} />
              ))}
            </div>
          </div>
        )}
        {state.manager.last_error && !busy && (
          <div className="mt-6 rounded-xl border border-red/20 bg-red-dim/40 px-4 py-3 text-[12.5px] text-red">
            Last generation problem: {state.manager.last_error}
            {state.manager.paused_until && " — background generation paused for a few minutes."}
          </div>
        )}
      </div>

      <aside className="space-y-5">
        {state.recall && <Recall card={state.recall} onDone={() => void load()} />}

        <Card className="p-5">
          <div className="flex items-baseline justify-between">
            <SectionLabel>Practice</SectionLabel>
            <span className="text-[12px] text-fg-2">{weekMinutes ? `${duration(weekMinutes * 60)} this week` : "nothing yet this week"}</span>
          </div>
          <div className="mt-4">
            <Heatmap days={state.calendar} />
          </div>
        </Card>

        <Link to="/atlas" className="block">
          <Card className="p-5 transition hover:border-line-strong">
            <div className="flex items-baseline justify-between">
              <SectionLabel>Atlas</SectionLabel>
              <span className="inline-flex items-center gap-1 text-[12px] text-fg-2">
                <MapIcon className="size-3.5" /> {uncovered ? `${uncovered} of ${atlas?.concepts.length} uncovered` : "all fog, for now"}
              </span>
            </div>
            <div className="mt-3">{atlas ? <HexMap regions={atlas.regions} concepts={atlas.concepts} mini /> : <div className="h-24" />}</div>
          </Card>
        </Link>

        <Link to="/playbook/orient" className="block">
          <Card className="flex items-center gap-3 p-4 transition hover:border-line-strong">
            <BookOpen className="size-4 text-teal" />
            <div className="text-[13px] text-fg-1">
              <span className="text-fg-0">Playbook:</span> the first 10 minutes in an unfamiliar codebase
            </div>
          </Card>
        </Link>
      </aside>
    </div>
  );
}

function FirstRun() {
  const steps = [
    { icon: <Mail className="size-4 text-blue" />, title: "A client reaches out", body: "Every client is a new company with a real-feeling Python codebase, a team, and a problem." },
    { icon: <Bug className="size-4 text-amber" />, title: "Recon, then the incident", body: "Explore first, answer a few questions, then a bug report lands. Find the root cause, fix it, prove it." },
    { icon: <Sparkles className="size-4 text-violet" />, title: "Debrief & grow", body: "See how an expert would have tracked it down, get a real code review, and watch your atlas light up." },
  ];
  return (
    <div className="mt-8 grid gap-3 sm:grid-cols-3">
      {steps.map((s, i) => (
        <motion.div key={s.title} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.1 + i * 0.08 } }}>
          <Card className="h-full p-4">
            <div className="flex items-center gap-2 text-[13.5px] font-medium text-fg-0">
              {s.icon}
              {s.title}
            </div>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-fg-2">{s.body}</p>
          </Card>
        </motion.div>
      ))}
    </div>
  );
}

function InboxCard({ card, disabled, onDismiss }: { card: CaseCard; disabled: boolean; onDismiss: () => void }) {
  const navigate = useNavigate();
  const Icon = channelIcon[card.channel] ?? Mail;
  const minutes = card.minutes.recon + card.minutes.incident;
  return (
    <div
      className={clsx(
        "group relative flex gap-4 rounded-2xl border border-line bg-ink-1 p-5 transition",
        !disabled && "cursor-pointer hover:border-line-strong hover:bg-ink-2",
      )}
      onClick={() => !disabled && navigate(`/case/${card.id}`)}
    >
      <Monogram name={card.company} size={46} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-3">
          <span className="font-serif text-[23px] leading-none text-fg-0">{card.company}</span>
          <span className="truncate text-[12.5px] text-fg-2">{card.industry}</span>
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-[11.5px] text-fg-3">
            <Icon className="size-3" />
            {card.arrived_at ? ago(card.arrived_at) : ""}
          </span>
        </div>
        <div className="mt-2 text-[15px] leading-snug text-fg-0">
          <span className="text-fg-3">“</span>
          {card.subject}
          <span className="text-fg-3">”</span>
        </div>
        <div className="mt-1 text-[12.5px] text-fg-2">
          from {card.from || "the team"} · {card.domain}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <Chip tone="amber">{fidelityLabel[card.fidelity] ?? card.fidelity}</Chip>
          <Chip>{card.shape}</Chip>
          <Chip mono>
            {card.stats.py_files} files · {card.stats.loc.toLocaleString()} lines
          </Chip>
          {card.libraries.map((l) => (
            <Chip key={l} tone="teal" mono>
              {l}
            </Chip>
          ))}
          <span className="ml-auto text-[12px] text-fg-2">~{minutes} min</span>
        </div>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          if (confirm(`Pass on ${card.company}? They won't come back — a new client will take their place.`)) onDismiss();
        }}
        className="absolute top-3 right-3 hidden rounded-md p-1 text-fg-3 group-hover:block hover:bg-ink-3 hover:text-fg-1"
        title="Pass on this client"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}

function PipelineRow({ item }: { item: PipelineItem }) {
  const progress = item.stage?.progress;
  return (
    <div className="flex items-center gap-4 rounded-xl border border-dashed border-line px-4 py-3">
      <Spinner className="size-3.5" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] text-fg-1">
          {item.domain ? <>A <span className="text-fg-0">{item.domain.toLowerCase()}</span> client</> : "A new client"}
          <span className="text-fg-3"> — </span>
          {item.status === "queued" ? "waiting in line" : item.stage?.label ?? "getting started"}
          {item.stage?.detail ? <span className="text-fg-3"> · {item.stage.detail}</span> : null}
        </div>
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-ink-3">
          {progress != null ? (
            <div className="h-full rounded-full bg-blue/70 transition-[width] duration-1000" style={{ width: `${progress * 100}%` }} />
          ) : (
            <div className="shimmer-bar h-full w-full" />
          )}
        </div>
      </div>
    </div>
  );
}

function Recall({ card, onDone }: { card: RecallCard; onDone: () => void }) {
  const [shown, setShown] = useState(false);
  const answer = async (remembered: boolean) => {
    await api.recall(card.id, remembered);
    setShown(false);
    onDone();
  };
  return (
    <Card className="overflow-hidden border-teal/20">
      <div className="bg-gradient-to-br from-teal-dim/80 to-transparent p-5">
        <SectionLabel className="text-teal">Quick recall</SectionLabel>
        <div className="mt-2 text-[14px] leading-relaxed text-fg-0">{card.recall_q}</div>
        {shown ? (
          <>
            <div className="mt-3 rounded-lg border border-line bg-ink-1/80 p-3">
              <Markdown>{card.recall_a}</Markdown>
            </div>
            <div className="mt-3 flex gap-2">
              <Button size="sm" tone="teal" onClick={() => void answer(true)}>
                Knew it
              </Button>
              <Button size="sm" onClick={() => void answer(false)}>
                Fuzzy — show me again soon
              </Button>
            </div>
          </>
        ) : (
          <Button size="sm" className="mt-3" onClick={() => setShown(true)}>
            Think, then reveal
          </Button>
        )}
      </div>
    </Card>
  );
}
