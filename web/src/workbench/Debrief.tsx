import clsx from "clsx";
import { motion } from "motion/react";
import { ArrowRight, BookMarked, Check, Footprints, Hammer, Link2, Lightbulb, MapPin, Sparkles, Telescope, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Button, Chip, Markdown, SectionLabel, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { ago, clock, stateLabel } from "../lib/format";
import type { ConceptCard, EngagementPayload, TaskKind, TaskResult } from "../lib/types";
import { useWB } from "./store";

const qualityTone: Record<string, "green" | "amber" | "red" | "neutral"> = {
  "root-cause": "green",
  partial: "amber",
  "symptom-patch": "amber",
  incorrect: "red",
  none: "neutral",
};
const verdictTone: Record<string, "green" | "amber" | "red" | "neutral"> = { correct: "green", partial: "amber", incorrect: "red", missing: "neutral" };

export default function Debrief({ data, kind, onClose }: { data: EngagementPayload; kind: TaskKind; onClose: () => void }) {
  const task = data.tasks[kind];
  const navigate = useNavigate();
  const { beginTask, refresh, openFile } = useWB.getState();
  const cached = task.result?.review ? task.result : null;
  const [explanation, setExplanation] = useState("");
  const [result, setResult] = useState<TaskResult | null>(cached);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lesson, setLesson] = useState(cached?.review?.lesson ?? "");
  const [ending, setEnding] = useState(false);
  const askFirst = kind === "incident" && !cached;

  const run = async (text: string) => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.debrief(task.id, text);
      setResult(r);
      setLesson(r.review?.lesson ?? "");
      void refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!askFirst && !cached) void run("");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const wrapUp = async () => {
    setEnding(true);
    await api.endEngagement(data.engagement.id);
    navigate(`/e/${data.engagement.id}/wrapup`);
  };
  const featureAvailable = kind === "incident" && ["pending", "skipped"].includes(data.tasks.feature.status);

  const r = result;
  const passed = task.status === "passed";
  const secs = r?.seconds ?? task.active_seconds;
  const par = r?.par_seconds ?? 0;
  const concept = r?.concept;
  const sol = r?.solution;

  return (
    <div className="fixed inset-0 z-40 overflow-y-auto bg-ink-0/95 backdrop-blur-sm">
      <button onClick={onClose} className="fixed top-4 right-5 z-10 rounded-lg p-2 text-fg-2 hover:bg-ink-3 hover:text-fg-0" title="Back to the code">
        <X className="size-5" />
      </button>
      <div className="mx-auto max-w-[920px] px-6 py-12">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <div className={clsx("text-[12px] font-semibold tracking-[0.12em] uppercase", kind === "incident" ? "text-amber" : "text-violet")}>
            {kind === "incident" ? "Incident debrief" : "Code review"} · {data.case.company.name}
          </div>
          <h1 className="mt-2 font-serif text-[46px] leading-[1.05] text-fg-0">
            {passed ? (kind === "incident" ? "Fixed." : "Shipped.") : "Here's what was going on."}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Chip tone={passed ? "green" : "neutral"}>{passed ? "all checks passing" : "solution revealed"}</Chip>
            <Chip mono>
              {clock(secs)}
              {par ? ` / par ${Math.round(par / 60)}m` : ""}
            </Chip>
            <Chip mono>{task.hints_used} hints</Chip>
            {task.attempts > 1 && <Chip mono>{task.attempts} submissions</Chip>}
            {concept && concept.before !== concept.state && (
              <Chip tone="blue">
                <Sparkles className="size-3" /> {stateLabel[concept.before]} → {stateLabel[concept.state]}
              </Chip>
            )}
          </div>
        </motion.div>

        {askFirst && !result && (
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0, transition: { delay: 0.15 } }} className="mt-10 rounded-2xl border border-line-strong bg-ink-1 p-6">
            <div className="text-[18px] font-medium text-fg-0">Before the reveal: what was the root cause?</div>
            <p className="mt-1 text-[13.5px] text-fg-2">
              One sentence, in your own words. Putting it into words is what turns a fix into something you'll recognize next time.
            </p>
            <textarea
              autoFocus
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
              rows={3}
              placeholder="The bug was… because…"
              className="mt-4 w-full resize-y rounded-xl border border-line-strong bg-ink-0 px-4 py-3 text-[14px] text-fg-0 outline-none placeholder:text-fg-3 focus:border-amber"
            />
            <div className="mt-4 flex items-center gap-3">
              <Button tone="amber" loading={loading} onClick={() => void run(explanation)} disabled={!explanation.trim() && !loading}>
                Show me the debrief
              </Button>
              <Button ghost onClick={() => void run("")} disabled={loading}>
                I'm not sure — just show me
              </Button>
            </div>
          </motion.div>
        )}

        {loading && (
          <div className="mt-10 flex items-center gap-3 text-[14px] text-fg-1">
            <Spinner /> {data.settings.mentor_name} is reviewing your work against the expert path…
          </div>
        )}
        {error && <div className="mt-6 rounded-xl border border-red/25 bg-red-dim/30 p-4 text-[13px] text-red">{error}</div>}

        {r?.review && sol && (
          <div className="mt-10 space-y-10">
            {kind === "incident" ? (
              <IncidentSections r={r} onOpen={(p, l) => { onClose(); void openFile(p, false, l, 1, "flash"); }} />
            ) : (
              <FeatureSections r={r} onOpen={(p, l) => { onClose(); void openFile(p, false, l, 1, "flash"); }} />
            )}

            {sol.concept_card && <ConceptCardView card={sol.concept_card} />}

            {r.previous_encounters && r.previous_encounters.length > 0 && (
              <Section icon={<Link2 className="size-4" />} title="You've met this before">
                <p className="text-[13px] text-fg-2">Same principle, different codebase. Compare them — the common thread is the thing to remember.</p>
                <div className="mt-3 space-y-2">
                  {r.previous_encounters.map((p) => (
                    <div key={p.case_id} className="rounded-xl border border-line bg-ink-1 p-3.5">
                      <div className="text-[13px] text-fg-0">
                        {p.company} <span className="text-fg-3">· {ago(p.when)}</span>
                      </div>
                      <div className="mt-0.5 text-[12.5px] text-fg-2 italic">“{p.subject}”</div>
                      <div className="mt-1.5 text-[13px] text-fg-1">{p.lesson}</div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              {r.review.strengths?.length > 0 && (
                <div className="rounded-2xl border border-green/15 bg-green-dim/20 p-5">
                  <SectionLabel className="text-green">What you did well</SectionLabel>
                  <ul className="mt-2 space-y-1.5">
                    {r.review.strengths.map((s, i) => (
                      <li key={i} className="flex gap-2 text-[13.5px] text-fg-1">
                        <Check className="mt-0.5 size-4 shrink-0 text-green" />
                        <Markdown className="text-[13.5px]">{s}</Markdown>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="rounded-2xl border border-teal/20 bg-teal-dim/30 p-5">
                <SectionLabel className="text-teal">Try this next time</SectionLabel>
                <Markdown className="mt-2 text-[14px] text-fg-0">{r.review.next_time}</Markdown>
              </div>
            </div>

            <Section icon={<BookMarked className="size-4" />} title="Your journal entry">
              <p className="text-[13px] text-fg-2">This is what comes back to you in quick-recall. Make it yours.</p>
              <textarea
                value={lesson}
                onChange={(e) => setLesson(e.target.value)}
                onBlur={() => r.journal_id && void api.updateJournal(r.journal_id, lesson)}
                rows={2}
                className="mt-3 w-full resize-y rounded-xl border border-line-strong bg-ink-1 px-4 py-3 text-[14px] text-fg-0 outline-none focus:border-blue"
              />
            </Section>

            <div className="flex flex-wrap items-center gap-3 border-t border-line pt-8">
              {featureAvailable && (
                <Button tone="violet" size="lg" icon={<Hammer className="size-4" />} onClick={() => { onClose(); void beginTask("feature"); }}>
                  Stay late: take the feature ticket
                </Button>
              )}
              <Button tone={featureAvailable ? "neutral" : "blue"} size="lg" loading={ending} icon={<ArrowRight className="size-4" />} onClick={() => void wrapUp()}>
                Wrap up this engagement
              </Button>
              <Button ghost onClick={onClose}>Back to the code</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="flex items-center gap-2 text-[15px] font-semibold text-fg-0">
        <span className="text-fg-2">{icon}</span>
        {title}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function DiffBlock({ title, diff, tone }: { title: string; diff: string; tone: "blue" | "green" }) {
  return (
    <div className="min-w-0">
      <div className={clsx("mb-1.5 text-[12px] font-medium", tone === "blue" ? "text-blue" : "text-green")}>{title}</div>
      <Markdown className="text-[12px]">{"```diff\n" + (diff.trim() || "(no changes)") + "\n```"}</Markdown>
    </div>
  );
}

function IncidentSections({ r, onOpen }: { r: TaskResult; onOpen: (path: string, line?: number) => void }) {
  const sol = r.solution!;
  const review = r.review!;
  return (
    <>
      <div className="rounded-2xl border border-amber/25 bg-gradient-to-br from-amber-dim/60 to-ink-1 p-6">
        <SectionLabel className="text-amber">Root cause</SectionLabel>
        <Markdown className="mt-2 text-[18px] leading-snug [&_p]:text-fg-0">{sol.root_cause}</Markdown>
        <button onClick={() => onOpen(sol.root_cause_file)} className="mt-3 inline-flex items-center gap-1.5 font-mono text-[12.5px] text-amber hover:underline">
          <MapPin className="size-3.5" /> {sol.root_cause_file} · {sol.root_cause_symbol}
        </button>
        {r.explanation && (
          <div className="mt-5 border-t border-amber/15 pt-4">
            <div className="flex items-center gap-2">
              <span className="text-[12px] text-fg-2">You said:</span>
              <Chip tone={verdictTone[review.explanation_verdict] ?? "neutral"}>{review.explanation_verdict}</Chip>
            </div>
            <div className="mt-1.5 text-[14px] text-fg-1 italic">“{r.explanation}”</div>
            <Markdown className="mt-2 text-[13px]">{review.explanation_feedback}</Markdown>
          </div>
        )}
      </div>

      <Section icon={<Lightbulb className="size-4" />} title="How it happens">
        <Markdown large>{sol.mechanism}</Markdown>
      </Section>

      <Section icon={<Hammer className="size-4" />} title="The fix">
        <div className="mb-3 flex items-center gap-2">
          <span className="text-[12.5px] text-fg-2">Your change:</span>
          <Chip tone={qualityTone[review.fix_quality] ?? "neutral"}>{review.fix_quality.replace("-", " ")}</Chip>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <DiffBlock title="Your diff" diff={r.learner_diff ?? ""} tone="blue" />
          <DiffBlock title="Canonical fix" diff={sol.fix_diff} tone="green" />
        </div>
        <Markdown className="mt-4">{review.fix_review}</Markdown>
        <div className="mt-4 rounded-xl border border-line bg-ink-1 p-4">
          <Markdown className="text-[13px]">{sol.fix}</Markdown>
        </div>
      </Section>

      <Section icon={<Footprints className="size-4" />} title="Your path vs. an expert's">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-line bg-ink-1 p-4">
            <div className="mb-2 text-[12px] font-medium text-blue">What you did</div>
            <pre className="max-h-80 overflow-y-auto font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap text-fg-2">{r.timeline}</pre>
          </div>
          <div className="rounded-xl border border-line bg-ink-1 p-4">
            <div className="mb-2 text-[12px] font-medium text-green">How an expert would go</div>
            <ol className="space-y-2.5">
              {sol.expert_path.map((s, i) => (
                <li key={i} className="flex gap-2.5">
                  <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-green-dim text-[10.5px] font-semibold text-green">{i + 1}</span>
                  <div className="min-w-0 text-[13px]">
                    <Markdown className="text-[13px] text-fg-0">{s.step}</Markdown>
                    <div className="mt-0.5 text-[12px] text-fg-2">{s.why}</div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
        <Markdown className="mt-4">{review.process_review}</Markdown>
      </Section>
    </>
  );
}

const severityTone = { blocker: "red", suggestion: "amber", nit: "neutral", praise: "green" } as const;

function FeatureSections({ r, onOpen }: { r: TaskResult; onOpen: (path: string, line?: number) => void }) {
  const review = r.review!;
  const sol = r.solution!;
  const verdict = { ship: ["green", "Approved"], "ship-with-nits": ["green", "Approved with nits"], "needs-work": ["amber", "Changes requested"] } as const;
  const [tone, label] = verdict[review.verdict] ?? ["neutral", review.verdict];
  return (
    <>
      <div className="rounded-2xl border border-violet/25 bg-gradient-to-br from-violet-dim/60 to-ink-1 p-6">
        <div className="flex items-center gap-2">
          <SectionLabel className="text-violet">Review</SectionLabel>
          <Chip tone={tone as "green"}>{label}</Chip>
        </div>
        <Markdown className="mt-2 text-[15px] text-fg-0">{review.summary}</Markdown>
      </div>

      {review.comments?.length > 0 && (
        <Section icon={<Telescope className="size-4" />} title="Line comments">
          <div className="space-y-2.5">
            {review.comments.map((c, i) => (
              <div key={i} className="rounded-xl border border-line bg-ink-1 p-3.5">
                <div className="flex items-center gap-2">
                  <Chip tone={severityTone[c.severity] ?? "neutral"}>{c.severity}</Chip>
                  <button onClick={() => onOpen(c.path, c.line)} className="font-mono text-[12px] text-blue hover:underline">
                    {c.path}:{c.line}
                  </button>
                </div>
                <Markdown className="mt-2 text-[13px]">{c.body}</Markdown>
              </div>
            ))}
          </div>
        </Section>
      )}

      {(review.idioms?.length > 0 || review.complexity) && (
        <Section icon={<Lightbulb className="size-4" />} title="Writing better Python">
          <div className="space-y-3">
            {review.idioms?.map((t, i) => (
              <div key={i} className="rounded-xl border border-line bg-ink-1 p-3.5">
                <Markdown className="text-[13px]">{t}</Markdown>
              </div>
            ))}
            {review.complexity && <Markdown className="text-[13.5px]">{review.complexity}</Markdown>}
          </div>
        </Section>
      )}

      <Section icon={<Hammer className="size-4" />} title="Yours vs. the reference">
        <div className="grid gap-4 lg:grid-cols-2">
          <DiffBlock title="Your diff" diff={r.learner_diff ?? ""} tone="blue" />
          <DiffBlock title="Reference implementation" diff={sol.reference_diff} tone="green" />
        </div>
        <Markdown className="mt-4">{review.process_review}</Markdown>
      </Section>
    </>
  );
}

function ConceptCardView({ card }: { card: ConceptCard }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-blue/25 bg-ink-1">
      <div className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-blue to-violet" />
      <div className="p-6 pl-7">
        <SectionLabel className="text-blue">Field guide</SectionLabel>
        <div className="mt-2 font-serif text-[30px] leading-tight text-fg-0">{card.headline}</div>
        <Markdown className="mt-3" large>{card.explanation}</Markdown>
        {card.example && <Markdown className="mt-3">{card.example.includes("```") ? card.example : "```python\n" + card.example + "\n```"}</Markdown>}
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <div className="text-[12px] font-semibold text-fg-1">Spot it fast</div>
            <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[13px] text-fg-2 marker:text-fg-3">
              {card.spot_it?.map((s, i) => <li key={i}><Markdown className="text-[13px]">{s}</Markdown></li>)}
            </ul>
          </div>
          <div>
            <div className="text-[12px] font-semibold text-fg-1">Also shows up in</div>
            <ul className="mt-1.5 list-disc space-y-1 pl-4 text-[13px] text-fg-2 marker:text-fg-3">
              {card.elsewhere?.map((s, i) => <li key={i}><Markdown className="text-[13px]">{s}</Markdown></li>)}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
