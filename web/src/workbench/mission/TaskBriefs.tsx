import clsx from "clsx";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, CircleAlert, Eye, FlaskConical, NotebookPen, Play, Send, Square, SquareCheck } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Avatar, Button, Chip, Markdown, SectionLabel } from "../../components/ui";
import { api } from "../../lib/api";
import { fidelityLabel } from "../../lib/format";
import type { EngagementPayload, SubmitResult, TaskKind } from "../../lib/types";
import { useWB } from "../store";
import Hints from "./Hints";
import Thread from "./Thread";

// --- shared submit flow ---------------------------------------------------------------

function SubmitBox({ taskId, kind, onPassed }: { taskId: string; kind: TaskKind; onPassed: () => void }) {
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [confirmReveal, setConfirmReveal] = useState(false);
  const { saveAll, flush, refresh, runTests, log } = useWB.getState();
  const testsRunning = useWB((s) => s.testsRunning);

  const submit = async () => {
    setSubmitting(true);
    setResult(null);
    try {
      await saveAll();
      await flush();
      const r = await api.submit(taskId);
      setResult(r);
      if (r.passed) {
        await refresh();
        onPassed();
      }
    } finally {
      setSubmitting(false);
    }
  };

  const reveal = async () => {
    await saveAll();
    await flush();
    await api.reveal(taskId);
    await refresh();
    onPassed();
  };

  const tone = kind === "incident" ? "amber" : "violet";
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <Button className="flex-1" icon={<Play className="size-3.5" />} loading={testsRunning} onClick={() => void runTests()}>
          Run tests
        </Button>
        <Button className="flex-1" tone={tone} icon={<Send className="size-3.5" />} loading={submitting} onClick={() => void submit()}>
          {kind === "incident" ? "Submit fix" : "Submit for review"}
        </Button>
      </div>
      <AnimatePresence>
        {result && !result.passed && (
          <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="rounded-xl border border-red/20 bg-red-dim/30 p-3.5">
            <div className="flex items-center gap-2 text-[13px] font-medium text-red">
              <CircleAlert className="size-4" />
              Not yet — {result.counts.failed + result.counts.errors} of {result.counts.total} checks failing
            </div>
            <div className="mt-2 space-y-2">
              {result.failing.slice(0, 6).map((f) => (
                <div key={f.nodeid} className="rounded-lg bg-ink-1/70 p-2.5">
                  <div className="flex items-center gap-1.5 font-mono text-[11.5px] text-fg-1">
                    {f.hidden ? <Chip tone="violet">client check</Chip> : <Chip>repo test</Chip>}
                    <span className="truncate">{f.nodeid.split("::").slice(-1)[0]}</span>
                  </div>
                  {f.message && <div className="mt-1 font-mono text-[11.5px] break-words text-fg-2">{f.message.slice(0, 300)}</div>}
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <span className="text-[12px] text-fg-2">Keep digging — or</span>
              {confirmReveal ? (
                <>
                  <Button size="sm" tone="red" onClick={() => void reveal()}>
                    Yes, show me the solution
                  </Button>
                  <Button size="sm" ghost onClick={() => setConfirmReveal(false)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button size="sm" ghost icon={<Eye className="size-3.5" />} onClick={() => { setConfirmReveal(true); log("reveal_considered", {}); }}>
                  Reveal solution
                </Button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {!result && (
        <div className="text-center">
          {confirmReveal ? (
            <span className="inline-flex items-center gap-2">
              <Button size="sm" tone="red" onClick={() => void reveal()}>
                Give up and see the solution
              </Button>
              <Button size="sm" ghost onClick={() => setConfirmReveal(false)}>
                Keep going
              </Button>
            </span>
          ) : (
            <button className="text-[11.5px] text-fg-3 hover:text-fg-2" onClick={() => setConfirmReveal(true)}>
              reveal solution
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// --- incident -------------------------------------------------------------------------

export function IncidentBrief({ data, onDone }: { data: EngagementPayload; onDone: () => void }) {
  const inc = data.case.incident!;
  const task = data.tasks.incident;
  const { openFile, runTests, log } = useWB.getState();
  const seenKey = `cs-thread-seen-${task.id}`;
  const [animate] = useState(() => {
    try {
      return !localStorage.getItem(seenKey);
    } catch {
      return false;
    }
  });
  const [ready, setReady] = useState(!animate);
  const [hypothesis, setHypothesis] = useState("");
  const [savedHyp, setSavedHyp] = useState(false);
  const onAllShown = useCallback(() => {
    setReady(true);
    try {
      localStorage.setItem(seenKey, "1");
    } catch {
      /* private mode */
    }
  }, [seenKey]);

  const saveHypothesis = () => {
    if (!hypothesis.trim()) return;
    log("hypothesis", { text: hypothesis.trim() });
    setSavedHyp(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Chip tone="amber">{fidelityLabel[inc.fidelity] ?? inc.fidelity}</Chip>
      </div>
      <Thread report={inc.report} animate={animate} onAllShown={onAllShown} />
      {ready && task.status === "active" && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
          {inc.regression_test && (
            <div className="flex gap-2">
              <Button size="sm" icon={<FlaskConical className="size-3.5" />} onClick={() => void openFile(inc.regression_test!)}>
                Open the failing test
              </Button>
              <Button size="sm" ghost icon={<Play className="size-3" />} onClick={() => void runTests([inc.regression_test!])}>
                Run it
              </Button>
            </div>
          )}
          {data.habit && (
            <div className="rounded-xl border border-teal/20 bg-teal-dim/25 px-3.5 py-2.5">
              <div className="text-[10.5px] font-semibold tracking-[0.08em] text-teal uppercase">Habit to practice</div>
              <Markdown className="mt-0.5 text-[12.5px]">{data.habit.text}</Markdown>
            </div>
          )}
          <div className="rounded-xl border border-line bg-ink-1 p-3.5">
            <div className="flex items-center gap-2 text-[12.5px] font-medium text-fg-1">
              <NotebookPen className="size-3.5 text-blue" /> First hypothesis
              {savedHyp && <CheckCircle2 className="ml-auto size-3.5 text-green" />}
            </div>
            <p className="mt-1 text-[11.5px] text-fg-3">Before digging: what do you think is going on, and what would confirm it? Guessing first makes you read with a purpose.</p>
            <textarea
              value={hypothesis}
              onChange={(e) => {
                setHypothesis(e.target.value);
                setSavedHyp(false);
              }}
              onBlur={saveHypothesis}
              rows={2}
              placeholder="e.g. the total is computed before the discount is applied — check checkout.py"
              className="mt-2 w-full resize-y rounded-lg border border-line-strong bg-ink-0 px-2.5 py-1.5 text-[12.5px] text-fg-0 outline-none placeholder:text-fg-3 focus:border-blue"
            />
          </div>
          <Hints taskId={task.id} seen={data.hints.incident ?? []} total={data.hint_total.incident} />
          <SubmitBox taskId={task.id} kind="incident" onPassed={onDone} />
        </motion.div>
      )}
    </div>
  );
}

// --- feature --------------------------------------------------------------------------

export function FeatureBrief({ data, onDone }: { data: EngagementPayload; onDone: () => void }) {
  const feat = data.case.feature!;
  const task = data.tasks.feature;
  const openFile = useWB.getState().openFile;
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const t = feat.ticket;
  const opened = useRef(false);

  useEffect(() => {
    if (!opened.current && task.status === "active") {
      opened.current = true;
      void openFile(feat.acceptance_path);
    }
  }, [task.status, feat.acceptance_path, openFile]);

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-xl border border-violet/20 bg-ink-2/50">
        <div className="border-b border-line bg-violet-dim/30 px-4 py-3">
          <div className="font-mono text-[11px] text-violet">{feat.title.split(":")[0]}</div>
          <div className="mt-0.5 text-[15px] leading-snug font-medium text-fg-0">{feat.title.split(":").slice(1).join(":").trim() || feat.title}</div>
          <div className="mt-2 flex items-center gap-2 text-[12px] text-fg-2">
            <Avatar name={feat.author.name} size={20} /> {feat.author.name}
            {feat.author.role && <span className="text-fg-3">· {feat.author.role}</span>}
          </div>
        </div>
        <div className="space-y-4 px-4 py-4">
          <Markdown className="text-[13px]">{t.background}</Markdown>
          {t.requirements?.length > 0 && (
            <div>
              <SectionLabel>Requirements</SectionLabel>
              <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[13px] text-fg-1 marker:text-fg-3">
                {t.requirements.map((r, i) => (
                  <li key={i}>
                    <Markdown className="text-[13px]">{r}</Markdown>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {t.acceptance?.length > 0 && (
            <div>
              <SectionLabel>Acceptance criteria</SectionLabel>
              <div className="mt-1.5 space-y-1">
                {t.acceptance.map((a, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      const next = new Set(checked);
                      if (next.has(i)) next.delete(i);
                      else next.add(i);
                      setChecked(next);
                    }}
                    className="flex w-full gap-2 rounded-md px-1 py-0.5 text-left hover:bg-ink-3"
                  >
                    {checked.has(i) ? <SquareCheck className="mt-0.5 size-4 shrink-0 text-violet" /> : <Square className="mt-0.5 size-4 shrink-0 text-fg-3" />}
                    <Markdown className={clsx("text-[13px]", checked.has(i) && "opacity-60")}>{a}</Markdown>
                  </button>
                ))}
              </div>
            </div>
          )}
          {t.interface && (
            <div>
              <SectionLabel>Interface</SectionLabel>
              <Markdown className="mt-1.5 text-[13px]">{t.interface}</Markdown>
            </div>
          )}
          {t.examples && (
            <div>
              <SectionLabel>Examples</SectionLabel>
              <Markdown className="mt-1.5 text-[13px]">{t.examples}</Markdown>
            </div>
          )}
          {t.out_of_scope?.length > 0 && (
            <div>
              <SectionLabel>Out of scope</SectionLabel>
              <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[12.5px] text-fg-2 marker:text-fg-3">
                {t.out_of_scope.map((o, i) => (
                  <li key={i}>{o}</li>
                ))}
              </ul>
            </div>
          )}
          {t.notes && (
            <div className="rounded-lg border border-line bg-ink-1 px-3 py-2">
              <Markdown className="text-[12.5px]">{t.notes}</Markdown>
            </div>
          )}
          <button onClick={() => void openFile(feat.acceptance_path)} className="font-mono text-[11.5px] text-violet hover:underline">
            {feat.acceptance_path}
          </button>
        </div>
      </div>
      {task.status === "active" && (
        <>
          <Hints taskId={task.id} seen={data.hints.feature ?? []} total={data.hint_total.feature} />
          <SubmitBox taskId={task.id} kind="feature" onPassed={onDone} />
        </>
      )}
    </div>
  );
}
