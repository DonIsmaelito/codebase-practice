import clsx from "clsx";
import { AnimatePresence, motion } from "motion/react";
import { Crosshair, Eye, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import HexMap, { REGION_COLORS } from "../components/HexMap";
import { Button, Card, Chip, Markdown, SectionLabel, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { ago, stateLabel } from "../lib/format";
import { usePageTitle } from "../lib/title";
import type { Concept, MasteryState, Region } from "../lib/types";

const STATES: MasteryState[] = ["fog", "glimpsed", "practiced", "solid", "mastered"];
const STATE_COPY: Record<MasteryState, string> = {
  fog: "Not met yet",
  glimpsed: "Seen in a codebase",
  practiced: "Solved it once",
  solid: "Solved again, spaced apart",
  mastered: "Held up after a long gap",
};

export default function Atlas() {
  usePageTitle("Atlas");
  const [data, setData] = useState<{ regions: Region[]; concepts: Concept[] } | null>(null);
  const [sel, setSel] = useState<Concept | null>(null);
  const [queued, setQueued] = useState<string | null>(null);

  useEffect(() => {
    api.atlas().then(setData);
  }, []);

  const counts = useMemo(() => {
    const c: Record<MasteryState, number> = { fog: 0, glimpsed: 0, practiced: 0, solid: 0, mastered: 0 };
    data?.concepts.forEach((x) => (c[x.state] += 1));
    return c;
  }, [data]);

  if (!data) return <div className="grid h-[60vh] place-items-center"><Spinner className="size-6" /></div>;

  const practice = async (c: Concept) => {
    await api.generate(c.id);
    setQueued(c.id);
  };

  return (
    <div className="mx-auto max-w-[1280px] px-6 py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-[42px] leading-none text-fg-0">Atlas</h1>
          <p className="mt-2 max-w-[640px] text-[14.5px] text-fg-1">
            Everything a working Python engineer runs into, as a map. Foundations sit at the heart of each island; advanced ideas on the shore. The fog lifts only when you've actually dealt with a concept in a real codebase.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[12px] text-fg-2">
          {STATES.map((s) => (
            <span key={s} className="flex items-center gap-1.5">
              <svg viewBox="0 0 12 12" className="size-3">
                <polygon points="6,0.5 11,3.3 11,8.7 6,11.5 1,8.7 1,3.3" fill={s === "fog" ? "#131722" : "#72b4ff"} fillOpacity={{ fog: 1, glimpsed: 0.16, practiced: 0.42, solid: 0.72, mastered: 1 }[s]} stroke={s === "fog" ? "#2a3143" : "#72b4ff"} />
              </svg>
              {stateLabel[s]} <span className="text-fg-3 tabular-nums">{counts[s]}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="h-fit p-4">
          <HexMap regions={data.regions} concepts={data.concepts} onSelect={setSel} selected={sel?.id} />
        </Card>

        <AnimatePresence mode="wait">
          {sel ? (
            <motion.div key={sel.id} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
              <Card className="sticky top-20 max-h-[calc(100vh-7rem)] overflow-y-auto p-5">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2 text-[11.5px] font-semibold tracking-[0.08em] uppercase" style={{ color: REGION_COLORS[sel.region] }}>
                      {data.regions.find((r) => r.id === sel.region)?.name} · tier {sel.tier}
                    </div>
                    <div className="mt-1 text-[20px] leading-snug font-semibold text-fg-0">{sel.name}</div>
                  </div>
                  <button onClick={() => setSel(null)} className="rounded p-1 text-fg-3 hover:bg-ink-3 hover:text-fg-0">
                    <X className="size-4" />
                  </button>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <Chip tone={sel.state === "fog" ? "neutral" : "blue"}>{stateLabel[sel.state]}</Chip>
                  <span className="text-[12px] text-fg-2">{STATE_COPY[sel.state]}</span>
                </div>
                {sel.state === "fog" ? (
                  <p className="mt-4 text-[13.5px] leading-relaxed text-fg-2">
                    Still in the fog. It'll reveal itself the first time it shows up in one of your engagements — no spoilers before then.
                  </p>
                ) : (
                  <>
                    <p className="mt-4 text-[14px] leading-relaxed text-fg-1">{sel.summary}</p>
                    {sel.beacons.length > 0 && (
                      <div className="mt-4">
                        <SectionLabel className="flex items-center gap-1.5"><Eye className="size-3.5" /> Spot it</SectionLabel>
                        <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[13px] text-fg-1 marker:text-fg-3">
                          {sel.beacons.map((b, i) => <li key={i}><Markdown className="text-[13px]">{b}</Markdown></li>)}
                        </ul>
                      </div>
                    )}
                    {sel.bug_patterns.length > 0 && (
                      <div className="mt-4">
                        <SectionLabel className="flex items-center gap-1.5"><Crosshair className="size-3.5" /> How it bites</SectionLabel>
                        <ul className="mt-1.5 list-disc space-y-1.5 pl-4 text-[12.5px] text-fg-2 marker:text-fg-3">
                          {sel.bug_patterns.map((b, i) => <li key={i}><Markdown className="text-[12.5px]">{b}</Markdown></li>)}
                        </ul>
                      </div>
                    )}
                    {sel.journal.length > 0 && (
                      <div className="mt-4">
                        <SectionLabel>From your journal</SectionLabel>
                        <div className="mt-2 space-y-2">
                          {sel.journal.map((j) => (
                            <div key={j.journal_id} className="rounded-lg border border-line bg-ink-2/60 p-3 text-[12.5px]">
                              <div className="text-fg-0">{j.lesson}</div>
                              <div className="mt-1 text-fg-3">{ago(j.when)}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
                <div className="mt-5 border-t border-line pt-4">
                  {queued === sel.id ? (
                    <div className="text-[13px] text-teal">A client with this kind of problem is on the way to your inbox.</div>
                  ) : (
                    <Button tone="blue" className="w-full" icon={<Sparkles className="size-4" />} onClick={() => void practice(sel)}>
                      Find me a client with this
                    </Button>
                  )}
                  <p className="mt-2 text-[11.5px] text-fg-3">The scheduler already brings concepts back on a spaced schedule; this jumps the queue.</p>
                </div>
              </Card>
            </motion.div>
          ) : (
            <motion.div key="regions" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <Card className="p-5">
                <SectionLabel>Regions</SectionLabel>
                <div className="mt-3 space-y-3">
                  {data.regions.map((r) => {
                    const cs = data.concepts.filter((c) => c.region === r.id);
                    const lit = cs.filter((c) => c.state !== "fog").length;
                    return (
                      <div key={r.id}>
                        <div className="flex items-center gap-2 text-[13px]">
                          <span className="size-2 rounded-full" style={{ background: REGION_COLORS[r.id] }} />
                          <span className="text-fg-0">{r.name}</span>
                          <span className="ml-auto text-[11.5px] text-fg-3 tabular-nums">{lit}/{cs.length}</span>
                        </div>
                        <div className="mt-0.5 pl-4 text-[12px] text-fg-2">{r.blurb}</div>
                      </div>
                    );
                  })}
                </div>
                <p className={clsx("mt-4 text-[12px] text-fg-3")}>Click any hex to inspect it.</p>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
