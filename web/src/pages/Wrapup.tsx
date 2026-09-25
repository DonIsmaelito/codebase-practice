import { motion } from "motion/react";
import { ArrowRight, Bug, Compass, Hammer } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { REGION_COLORS } from "../components/HexMap";
import { Avatar, Button, Card, Chip, Monogram, SectionLabel, Spinner } from "../components/ui";
import { api, type WrapupPayload } from "../lib/api";
import { useDesk } from "../lib/desk";
import { duration, stateLabel } from "../lib/format";
import type { CaseCard } from "../lib/types";

export default function Wrapup() {
  const { eid } = useParams();
  const [data, setData] = useState<WrapupPayload | null>(null);
  const loadDesk = useDesk((s) => s.load);

  useEffect(() => {
    if (eid) api.wrapup(eid).then(setData);
    void loadDesk();
  }, [eid, loadDesk]);

  if (!data) return <div className="grid h-[60vh] place-items-center"><Spinner className="size-6" /></div>;

  const inc = data.tasks.incident;
  const feat = data.tasks.feature;
  const recon = data.tasks.recon;
  const thanker = data.company.team[0];
  const lines = [
    inc.status === "passed" ? "The fix is in and everything's behaving again — thank you." : inc.status === "revealed" ? "We've got the fix merged. Thanks for digging in with us." : "Thanks for jumping in.",
    feat.status === "passed" ? "And the feature landed too. The team's already using it." : null,
    "Let's work together again sometime.",
  ].filter(Boolean);
  const total = (recon.active_seconds ?? 0) + (inc.active_seconds ?? 0) + (feat.active_seconds ?? 0);
  const next = data.next ? ({ id: data.next.id, ...JSON.parse(data.next.card) } as CaseCard) : null;

  const rows = [
    { icon: <Compass className="size-4 text-blue" />, label: "Recon", t: recon, extra: recon.result?.accuracy != null ? `${Math.round(recon.result.accuracy * 100)}% of your map held up` : null },
    { icon: <Bug className="size-4 text-amber" />, label: "Incident", t: inc, extra: inc.result?.outcome ?? null },
    { icon: <Hammer className="size-4 text-violet" />, label: "Feature", t: feat, extra: feat.result?.outcome ?? null },
  ].filter((r) => !["pending", "skipped"].includes(r.t.status));

  return (
    <div className="mx-auto max-w-[860px] px-6 py-12">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-5">
        <Monogram name={data.company.name} size={64} />
        <div>
          <div className="text-[12px] font-semibold tracking-[0.12em] text-green uppercase">Engagement complete</div>
          <h1 className="mt-1 font-serif text-[46px] leading-none text-fg-0">{data.company.name}</h1>
        </div>
      </motion.div>

      {thanker && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.15 } }} className="mt-8 flex gap-3">
          <Avatar name={thanker.name} size={34} />
          <div className="rounded-2xl rounded-tl-sm border border-line bg-ink-1 px-4 py-3">
            <div className="text-[13px] font-semibold text-fg-0">{thanker.name} <span className="font-normal text-fg-2">· {thanker.role}</span></div>
            <div className="mt-1 text-[14px] leading-relaxed text-fg-1">{lines.join(" ")}</div>
          </div>
        </motion.div>
      )}

      <Card className="mt-8 p-6">
        <div className="flex items-baseline justify-between">
          <SectionLabel>Tonight</SectionLabel>
          <span className="text-[12.5px] text-fg-2">{duration(total)} focused</span>
        </div>
        <div className="mt-3 divide-y divide-line/70">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center gap-3 py-2.5">
              {r.icon}
              <span className="text-[13.5px] text-fg-0">{r.label}</span>
              {r.extra && <Chip>{r.extra}</Chip>}
              <span className="ml-auto text-[12.5px] text-fg-2 tabular-nums">{duration(r.t.active_seconds)}</span>
            </div>
          ))}
        </div>
      </Card>

      {data.concepts.some((c) => c.mastery !== "fog") && (
        <Card className="mt-6 p-6">
          <SectionLabel>On your atlas</SectionLabel>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {data.concepts.filter((c) => c.mastery !== "fog").map((c, i) => (
              <motion.div key={c.id} initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1, transition: { delay: 0.3 + i * 0.12 } }} className="flex items-center gap-3 rounded-xl border border-line bg-ink-2/50 px-3 py-2.5">
                <svg viewBox="0 0 12 12" className="size-4 shrink-0">
                  <polygon points="6,0.5 11,3.3 11,8.7 6,11.5 1,8.7 1,3.3" fill={REGION_COLORS[c.region]} fillOpacity={{ fog: 0.1, glimpsed: 0.25, practiced: 0.5, solid: 0.8, mastered: 1 }[c.mastery] ?? 0.2} stroke={REGION_COLORS[c.region]} />
                </svg>
                <div className="min-w-0">
                  <div className="truncate text-[13px] text-fg-0">{c.name}</div>
                  <div className="text-[11.5px] text-fg-2">{stateLabel[c.mastery] ?? c.mastery}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </Card>
      )}

      <div className="mt-10">
        {next ? (
          <Link to={`/case/${next.id}`} className="group block rounded-2xl border border-line bg-gradient-to-r from-ink-2 to-ink-1 p-5 transition hover:border-line-strong">
            <div className="text-[12px] text-fg-2">Next in your inbox</div>
            <div className="mt-2 flex items-center gap-4">
              <Monogram name={next.company} size={42} />
              <div className="min-w-0 flex-1">
                <div className="font-serif text-[22px] leading-none text-fg-0">{next.company}</div>
                <div className="mt-1 truncate text-[13.5px] text-fg-1">“{next.subject}”</div>
              </div>
              <ArrowRight className="size-5 text-fg-2 transition group-hover:translate-x-1 group-hover:text-fg-0" />
            </div>
          </Link>
        ) : (
          <Link to="/"><Button tone="blue" size="lg">Back to the desk</Button></Link>
        )}
      </div>
    </div>
  );
}
