import clsx from "clsx";
import { motion } from "motion/react";
import { ArrowLeft, Bug, Check, Compass, Hammer } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Avatar, Button, Card, Chip, Monogram, SectionLabel, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useDesk } from "../lib/desk";
import { channelLabel, fidelityLabel } from "../lib/format";
import { usePageTitle } from "../lib/title";
import type { CaseCard, Company, TaskKind } from "../lib/types";

interface Preview {
  id: string;
  status: string;
  company: Company;
  repo: { name: string; package: string; shape: string; summary: string; entry_points: string[]; libraries: string[]; stats: CaseCard["stats"] };
  card: CaseCard;
  recon_mode: string;
  default_plan: TaskKind[];
}

const reconCopy: Record<string, string> = {
  guided: "A teammate gives you a guided tour, then a few questions with the code open.",
  open: "Explore on your own (the tour is there if you need it), then answer a few questions.",
  closed: "Scout the code for a few minutes, then answer from memory — the code hides while you answer.",
};

export default function Briefing() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const load = useDesk((s) => s.load);
  const [p, setP] = useState<Preview | null>(null);
  const [plan, setPlan] = useState<Set<TaskKind>>(new Set(["recon", "incident"]));
  const [starting, setStarting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  usePageTitle(p?.company.name);

  useEffect(() => {
    fetch(`/api/cases/${caseId}`)
      .then((r) => r.json())
      .then((data: Preview) => {
        setP(data);
        setPlan(new Set(data.default_plan?.length ? data.default_plan : ["recon", "incident"]));
      });
  }, [caseId]);

  if (!p) return <div className="grid h-[60vh] place-items-center"><Spinner className="size-6" /></div>;

  const toggle = (k: TaskKind) => {
    if (k === "incident") return;
    const next = new Set(plan);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setPlan(next);
  };
  const total = (plan.has("recon") ? p.card.minutes.recon : 0) + p.card.minutes.incident + (plan.has("feature") ? p.card.minutes.feature : 0);

  const start = async () => {
    setStarting(true);
    setErr(null);
    try {
      const data = await api.startEngagement(p.id, ["recon", "incident", "feature"].filter((k) => plan.has(k as TaskKind)) as TaskKind[]);
      void load();
      navigate(`/e/${data.engagement.id}`);
    } catch (e) {
      setErr((e as Error).message);
      setStarting(false);
    }
  };

  const steps: { kind: TaskKind; icon: React.ReactNode; title: string; body: string; minutes: number; tone: string; locked?: boolean }[] = [
    { kind: "recon", icon: <Compass className="size-4" />, title: "Recon", body: reconCopy[p.recon_mode] ?? reconCopy.open, minutes: p.card.minutes.recon, tone: "text-blue border-blue/30 bg-blue-dim" },
    { kind: "incident", icon: <Bug className="size-4" />, title: "The incident", body: `${channelLabel[p.card.channel] ?? "A message"} from ${p.card.from || "the team"}: “${p.card.subject}”. Find the root cause, fix it, prove it.`, minutes: p.card.minutes.incident, tone: "text-amber border-amber/30 bg-amber-dim", locked: true },
    { kind: "feature", icon: <Hammer className="size-4" />, title: "Feature ticket (optional)", body: "Stay late and ship a feature from a real spec, then get a line-by-line code review.", minutes: p.card.minutes.feature, tone: "text-violet border-violet/30 bg-violet-dim" },
  ];

  return (
    <div className="mx-auto max-w-[980px] px-6 py-10">
      <Link to="/" className="inline-flex items-center gap-1.5 text-[13px] text-fg-2 hover:text-fg-0">
        <ArrowLeft className="size-3.5" /> Inbox
      </Link>

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mt-6 flex items-start gap-6">
        <Monogram name={p.company.name} size={76} />
        <div className="min-w-0">
          <div className="text-[12px] font-medium tracking-[0.1em] text-fg-2 uppercase">Client file · {p.company.industry}</div>
          <h1 className="mt-1 font-serif text-[52px] leading-[1] tracking-tight text-fg-0">{p.company.name}</h1>
          <div className="mt-2 font-serif text-[20px] text-fg-1 italic">{p.company.tagline}</div>
        </div>
      </motion.div>

      <p className="mt-6 max-w-[720px] text-[15.5px] leading-relaxed text-fg-1">{p.company.blurb}</p>

      <div className="mt-8 grid gap-4 md:grid-cols-[1fr_300px]">
        <Card className="p-5">
          <SectionLabel>The codebase</SectionLabel>
          <div className="mt-2 font-mono text-[14px] text-fg-0">{p.repo.name}</div>
          <p className="mt-2 text-[13.5px] leading-relaxed text-fg-1">{p.repo.summary}</p>
          <div className="mt-4 flex flex-wrap gap-1.5">
            <Chip>{p.repo.shape}</Chip>
            <Chip mono>{p.repo.stats.py_files} modules</Chip>
            <Chip mono>{p.repo.stats.loc.toLocaleString()} lines</Chip>
            <Chip mono>{p.repo.stats.test_files} test files</Chip>
            {p.repo.libraries.map((l) => (
              <Chip key={l} tone="teal" mono>{l}</Chip>
            ))}
            <Chip tone="amber">{fidelityLabel[p.card.fidelity] ?? p.card.fidelity}</Chip>
          </div>
        </Card>
        <Card className="p-5">
          <SectionLabel>You'll hear from</SectionLabel>
          <div className="mt-3 space-y-3">
            {p.company.team.map((m) => (
              <div key={m.name} className="flex items-center gap-3">
                <Avatar name={m.name} size={30} />
                <div className="min-w-0">
                  <div className="truncate text-[13.5px] text-fg-0">{m.name}</div>
                  <div className="truncate text-[12px] text-fg-2">{m.role}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-10">
        <SectionLabel>Tonight's plan</SectionLabel>
        <div className="mt-3 space-y-2.5">
          {steps.map((s) => {
            const on = plan.has(s.kind);
            return (
              <button
                key={s.kind}
                onClick={() => toggle(s.kind)}
                className={clsx(
                  "flex w-full items-start gap-4 rounded-2xl border p-4 text-left transition",
                  on ? "border-line-strong bg-ink-2" : "border-line bg-ink-1 opacity-60 hover:opacity-90",
                  s.locked && "cursor-default",
                )}
              >
                <span className={clsx("grid size-8 shrink-0 place-items-center rounded-lg border", s.tone)}>{s.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-3">
                    <span className="text-[14.5px] font-medium text-fg-0">{s.title}</span>
                    <span className="text-[12px] text-fg-2">~{s.minutes} min</span>
                  </div>
                  <div className="mt-0.5 text-[13px] leading-relaxed text-fg-2">{s.body}</div>
                </div>
                <span className={clsx("mt-1 grid size-5 shrink-0 place-items-center rounded-md border", on ? "border-blue bg-blue text-ink-0" : "border-line-strong")}>
                  {on && <Check className="size-3.5" strokeWidth={3} />}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-8 flex items-center gap-4">
        <Button tone="amber" size="lg" loading={starting} onClick={() => void start()} disabled={p.status !== "ready"}>
          Clock in · ~{total} min
        </Button>
        <span className="text-[12.5px] text-fg-2">The timer only runs while you're working. You can pause anytime.</span>
      </div>
      {p.status !== "ready" && <div className="mt-3 text-[13px] text-fg-2">This client has already been taken.</div>}
      {err && <div className="mt-3 text-[13px] text-red">{err}</div>}
    </div>
  );
}
