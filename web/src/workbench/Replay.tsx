import clsx from "clsx";
import { AnimatePresence, motion } from "motion/react";
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  FileCode2,
  Hammer,
  Lightbulb,
  type LucideIcon,
  Pause,
  Play,
  RotateCcw,
  Search,
  SquareTerminal,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Avatar, Button, Markdown, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { basename, clock, languageFor } from "../lib/format";
import { monaco, THEME } from "../lib/monaco";
import type { Report, ReplayPayload, ReplayStep } from "../lib/types";

const KINDS: Record<ReplayStep["kind"], { icon: LucideIcon; tone: string }> = {
  read: { icon: FileCode2, tone: "text-blue" },
  search: { icon: Search, tone: "text-amber" },
  run: { icon: SquareTerminal, tone: "text-violet" },
  think: { icon: Lightbulb, tone: "text-teal" },
  fix: { icon: Hammer, tone: "text-green" },
  verify: { icon: CheckCircle2, tone: "text-green" },
};

const SPEEDS = [1, 1.5, 2];

/** Narration without markdown punctuation, for one-line summaries. */
const plain = (text: string) => text.replace(/[*_`]+/g, "");

function label(s: ReplayStep): string {
  switch (s.kind) {
    case "read":
      return `${basename(s.path ?? "")}:${s.line}`;
    case "search":
      return `search “${s.query}”`;
    case "run":
    case "verify":
      return `$ ${s.command}`;
    case "fix":
      return "the fix";
    default:
      return "thinking";
  }
}

/** How long a step stays on screen at 1x: long enough to read the narration and output. */
function durationOf(s: ReplayStep): number {
  let ms = 2200 + s.say.length * 50;
  if (s.output) ms += Math.min(6000, s.output.split("\n").length * 140);
  if (s.kind === "fix") ms += 3500;
  if (s.kind === "search") ms += 1200;
  return Math.max(5000, Math.min(18000, ms));
}

/** The file on screen at step i: the latest read, or the first hit of the latest search. */
function viewAt(steps: ReplayStep[], i: number): { step: ReplayStep; path: string; line: number } | null {
  for (let j = i; j >= 0; j--) {
    const s = steps[j];
    if (s.kind === "read" && s.path) return { step: s, path: s.path, line: s.line ?? 1 };
    if (s.kind === "search" && s.hits?.length) return { step: s, path: s.hits[0].path, line: s.hits[0].line };
  }
  return null;
}

/** Watch an expert work the incident you just finished: files open, lines light up,
 *  commands run with their real output, and the narration says what they're thinking. */
export default function Replay({ taskId, mentorName, company, report, onClose }: { taskId: string; mentorName: string; company: string; report?: Report; onClose: () => void }) {
  const [data, setData] = useState<ReplayPayload | null>(null);

  useEffect(() => {
    let alive = true;
    let timer = 0;
    const load = async () => {
      try {
        const r = await api.replay(taskId);
        if (!alive) return;
        setData(r);
        if (r.status === "generating") timer = window.setTimeout(() => void load(), 3000);
      } catch (e) {
        if (alive) setData({ status: "failed", error: (e as Error).message });
      }
    };
    void load();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [taskId]);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="fixed inset-0 z-50 flex flex-col bg-ink-0">
      {data?.status === "ready" && data.steps?.length ? (
        <Player data={data} mentorName={mentorName} company={company} report={report} onClose={onClose} />
      ) : (
        <div className="relative grid flex-1 place-items-center">
          <button onClick={onClose} className="absolute top-4 right-5 rounded-lg p-2 text-fg-2 hover:bg-ink-3 hover:text-fg-0" title="Close">
            <X className="size-5" />
          </button>
          <div className="max-w-md text-center">
            <Avatar name={mentorName} size={44} />
            {!data || data.status === "generating" ? (
              <>
                <div className="mt-4 flex items-center justify-center gap-2 text-[16px] text-fg-0">
                  <Spinner /> {mentorName} is recording the replay…
                </div>
                <p className="mt-2 text-[13px] text-fg-2">
                  Every command in it is run for real against {company}'s code, so it takes about a minute.
                </p>
              </>
            ) : (
              <>
                <div className="mt-4 text-[16px] text-fg-0">The replay couldn't be recorded right now.</div>
                {data.error && <p className="mt-2 text-[12.5px] break-words text-red">{data.error}</p>}
                <Button className="mt-4" onClick={onClose}>
                  Back
                </Button>
              </>
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}

function Player({ data, mentorName, company, report, onClose }: { data: ReplayPayload; mentorName: string; company: string; report?: Report; onClose: () => void }) {
  const steps = data.steps!;
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [done, setDone] = useState(false);
  const step = steps[i];

  const go = useCallback(
    (n: number) => {
      if (n >= steps.length) {
        setDone(true);
        setPlaying(false);
        return;
      }
      setDone(false);
      setI(Math.max(0, n));
    },
    [steps.length],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === " ") setPlaying((p) => !p);
      else if (e.key === "ArrowRight") go(i + 1);
      else if (e.key === "ArrowLeft") go(i - 1);
      else return;
      e.preventDefault();
      e.stopPropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [i, go, onClose]);

  return (
    <>
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-4">
        <Avatar name={mentorName} size={26} />
        <div className="min-w-0">
          <span className="font-serif text-[17px] text-fg-0">{mentorName} works the incident</span>
          <span className="ml-2 text-[12px] text-fg-3">{company}</span>
        </div>
        <div className="mx-auto flex items-center gap-1">
          <IconButton title="Previous (←)" onClick={() => go(i - 1)} disabled={i === 0}>
            <ChevronLeft className="size-4" />
          </IconButton>
          <IconButton
            title={playing ? "Pause (space)" : "Play (space)"}
            onClick={() => (done ? (go(0), setPlaying(true)) : setPlaying((p) => !p))}
            primary
          >
            {done ? <RotateCcw className="size-4" /> : playing ? <Pause className="size-4" /> : <Play className="size-4" />}
          </IconButton>
          <IconButton title="Next (→)" onClick={() => go(i + 1)}>
            <ChevronRight className="size-4" />
          </IconButton>
          <button
            onClick={() => setSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length])}
            className="ml-1 w-11 rounded-md py-1 font-mono text-[12px] text-fg-2 hover:bg-ink-3 hover:text-fg-0"
            title="Playback speed"
          >
            {speed}×
          </button>
        </div>
        <span className="font-mono text-[12px] text-fg-3 tabular-nums">
          {i + 1}/{steps.length}
        </span>
        <button onClick={onClose} className="rounded-lg p-1.5 text-fg-2 hover:bg-ink-3 hover:text-fg-0" title="Close (Esc)">
          <X className="size-5" />
        </button>
      </header>
      <Progress key={`${i}-${done}`} steps={steps} index={i} playing={playing && !done} speed={speed} done={done} onDone={() => go(i + 1)} onJump={go} />
      <div className="flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1">
          <Stage steps={steps} index={i} data={data} report={report} />
          <AnimatePresence>{done && <EndCard data={data} mentorName={mentorName} onAgain={() => { go(0); setPlaying(true); }} onClose={onClose} />}</AnimatePresence>
        </div>
        <aside className="flex w-[400px] shrink-0 flex-col border-l border-line bg-ink-1">
          <Script steps={steps} index={i} done={done} onJump={(n) => go(n)} />
        </aside>
      </div>
      <div className="h-0">{step && null}</div>
    </>
  );
}

function IconButton({ children, primary, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { primary?: boolean }) {
  return (
    <button
      {...rest}
      className={clsx(
        "grid size-8 place-items-center rounded-lg transition disabled:opacity-30",
        primary ? "bg-green text-ink-0 hover:brightness-110" : "text-fg-1 hover:bg-ink-3 hover:text-fg-0",
      )}
    >
      {children}
    </button>
  );
}

/** Story-style segmented progress; drives auto-advance while playing. */
function Progress({ steps, index, playing, speed, done, onDone, onJump }: {
  steps: ReplayStep[]; index: number; playing: boolean; speed: number; done: boolean; onDone: () => void; onJump: (n: number) => void;
}) {
  const [p, setP] = useState(0);
  const elapsed = useRef(0);
  useEffect(() => {
    if (!playing) return;
    const total = durationOf(steps[index]) / speed;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      elapsed.current += now - last;
      last = now;
      const next = Math.min(1, elapsed.current / total);
      setP(next);
      if (next >= 1) onDone();
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, index, steps, onDone]);
  return (
    <div className="flex h-1.5 shrink-0 gap-1 bg-ink-0 px-4 pt-0.5">
      {steps.map((s, n) => (
        <button key={n} onClick={() => onJump(n)} className="h-full flex-1 overflow-hidden rounded-full bg-ink-3" title={label(s)}>
          <div className="h-full rounded-full bg-green" style={{ width: `${done || n < index ? 100 : n === index ? p * 100 : 0}%` }} />
        </button>
      ))}
    </div>
  );
}

const EDITOR: monaco.editor.IStandaloneEditorConstructionOptions = {
  theme: THEME,
  fontFamily: '"JetBrains Mono Variable", ui-monospace, Menlo, monospace',
  fontSize: 14,
  lineHeight: 22,
  readOnly: true,
  domReadOnly: true,
  automaticLayout: true,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  smoothScrolling: true,
  renderLineHighlight: "none",
  stickyScroll: { enabled: true, maxLineCount: 2 },
  padding: { top: 12, bottom: 12 },
  scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10, useShadows: false },
  overviewRulerBorder: false,
  contextmenu: false,
};

/** The editor (and terminal) as the expert sees them at this step. */
function Stage({ steps, index, data, report }: { steps: ReplayStep[]; index: number; data: ReplayPayload; report?: Report }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const diffRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const decoRef = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);
  const models = useRef(new Map<string, monaco.editor.ITextModel>());
  const step = steps[index];
  const view = viewAt(steps, index);
  const fixPath = Object.keys(data.fixed ?? {})[0];
  const showDiff = step.kind === "fix" && !!fixPath && !!data.files?.[fixPath];
  const showTerminal = (step.kind === "run" || step.kind === "verify") && step.output !== undefined;

  // One read-only editor over the code as it was deployed (bug included).
  useEffect(() => {
    if (!hostRef.current) return;
    const own = new Map<string, monaco.editor.ITextModel>();
    const make = (key: string, path: string, content: string) => {
      const uri = monaco.Uri.from({ scheme: "file", path: `/${key}/${path}` });
      monaco.editor.getModel(uri)?.dispose();
      own.set(`${key}:${path}`, monaco.editor.createModel(content, languageFor(path), uri));
    };
    for (const [path, content] of Object.entries(data.files ?? {})) make("replay", path, content);
    for (const [path, content] of Object.entries(data.fixed ?? {})) make("replay-fixed", path, content);
    models.current = own;
    const editor = monaco.editor.create(hostRef.current, { ...EDITOR, model: null });
    editorRef.current = editor;
    decoRef.current = editor.createDecorationsCollection();
    return () => {
      editor.dispose();
      for (const m of own.values()) m.dispose();
      editorRef.current = null;
    };
  }, [data]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || !view) return;
    const model = models.current.get(`replay:${view.path}`);
    if (!model) return;
    if (editor.getModel() !== model) editor.setModel(model);
    const s = view.step;
    if (s.kind === "read") {
      const end = s.end_line ?? view.line;
      editor.revealLinesInCenter(view.line, end, monaco.editor.ScrollType.Smooth);
      decoRef.current?.set(
        s.end_line
          ? [{ range: new monaco.Range(view.line, 1, end, 1), options: { isWholeLine: true, className: "cs-replay-line", linesDecorationsClassName: "cs-replay-glyph" } }]
          : [],
      );
    } else if (s.kind === "search" && s.query) {
      const matches = model.findMatches(s.query, false, false, true, null, false);
      editor.revealLineInCenter(view.line, monaco.editor.ScrollType.Smooth);
      decoRef.current?.set(matches.map((m) => ({ range: m.range, options: { inlineClassName: "cs-replay-hit" } })));
    }
  }, [view?.step, view?.path, view?.line]); // eslint-disable-line react-hooks/exhaustive-deps

  // The fix, as a diff over the file it touches.
  useEffect(() => {
    if (!showDiff || !diffRef.current) return;
    const original = models.current.get(`replay:${fixPath}`);
    const modified = models.current.get(`replay-fixed:${fixPath}`);
    if (!original || !modified) return;
    const diff = monaco.editor.createDiffEditor(diffRef.current, {
      ...EDITOR,
      renderSideBySide: false,
      renderOverviewRuler: false,
      hideUnchangedRegions: { enabled: true, contextLineCount: 4 },
    });
    diff.setModel({ original, modified });
    return () => {
      diff.setModel(null);
      diff.dispose();
    };
  }, [showDiff, fixPath]);

  return (
    <div className="flex h-full flex-col bg-ink-1">
      <div className="flex h-9 shrink-0 items-center gap-2 border-b border-line bg-ink-0 px-4 font-mono text-[12px] text-fg-1">
        {showDiff ? (
          <span className="text-green">{fixPath} · the fix</span>
        ) : view ? (
          <>
            <FileCode2 className="size-3.5 text-fg-3" />
            {view.path}
            <span className="text-fg-3">· as deployed, bug included</span>
          </>
        ) : (
          <span className="text-fg-3">no code yet</span>
        )}
      </div>
      <div className="relative min-h-0 flex-1">
        <div ref={hostRef} className={clsx("absolute inset-0", (showDiff || !view) && "invisible")} />
        {showDiff && <div ref={diffRef} className="absolute inset-0" />}
        {!view && !showDiff && (
          <div className="absolute inset-0 overflow-y-auto px-8 py-6">
            {report ? (
              <div className="mx-auto max-w-2xl space-y-4">
                <div className="text-[11px] font-semibold tracking-[0.1em] text-amber uppercase">The report, read slowly</div>
                {report.messages.map((m, k) => (
                  <div key={k} className="flex gap-3">
                    <Avatar name={m.from} size={28} />
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] font-semibold text-fg-0">
                        {m.from} <span className="font-normal text-fg-3">{m.role}</span>
                      </div>
                      <Markdown className="mt-0.5 text-[14px]">{m.body}</Markdown>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid h-full place-items-center text-[13px] text-fg-3">Nothing open yet — first, the report.</div>
            )}
          </div>
        )}
        <AnimatePresence>
          {showTerminal && (
            <motion.div
              key={index}
              initial={{ y: 40, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 40, opacity: 0 }}
              className="absolute inset-x-0 bottom-0 flex max-h-[55%] flex-col border-t border-line-strong bg-ink-0/95 backdrop-blur"
            >
              <div className="flex h-7 shrink-0 items-center gap-1.5 border-b border-line px-3 text-[11px] text-fg-3">
                <SquareTerminal className="size-3" /> terminal {step.kind === "verify" && <span className="text-green">· with the fix applied</span>}
              </div>
              <Typed key={index} command={step.command ?? ""} output={step.output ?? ""} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

/** The command types itself out, then its real output appears. */
function Typed({ command, output }: { command: string; output: string }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (n >= command.length) return;
    const id = window.setTimeout(() => setN((x) => Math.min(command.length, x + 3)), 16);
    return () => window.clearTimeout(id);
  }, [n, command.length]);
  return (
    <pre className="min-h-0 flex-1 overflow-auto px-4 py-3 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap">
      <span className="text-green">$ </span>
      <span className="text-fg-0">{command.slice(0, n)}</span>
      {n >= command.length && <span className="block pt-1 text-fg-1">{output}</span>}
    </pre>
  );
}

/** The script: every step, the current one expanded with the narration. */
function Script({ steps, index, done, onJump }: { steps: ReplayStep[]; index: number; done: boolean; onJump: (n: number) => void }) {
  const current = useRef<HTMLLIElement>(null);
  useEffect(() => {
    current.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [index]);
  return (
    <ol className="min-h-0 flex-1 space-y-1 overflow-y-auto p-3">
      {steps.map((s, n) => {
        const K = KINDS[s.kind];
        const isNow = n === index && !done;
        const future = n > index && !done;
        return (
          <li key={n} ref={n === index ? current : undefined}>
            <button
              onClick={() => onJump(n)}
              className={clsx(
                "w-full rounded-xl px-3 py-2 text-left transition",
                isNow ? "border border-green/25 bg-ink-2" : "border border-transparent hover:bg-ink-2/60",
                future && "opacity-45",
              )}
            >
              <div className="flex items-center gap-2">
                <K.icon className={clsx("size-3.5 shrink-0", K.tone)} />
                <span className={clsx("min-w-0 flex-1 truncate font-mono text-[11.5px]", isNow ? "text-fg-0" : "text-fg-2")}>{label(s)}</span>
                <span className="shrink-0 font-mono text-[11px] text-fg-3 tabular-nums">{clock(s.at)}</span>
              </div>
              {(s.kind === "read" || s.kind === "search") && !future && <You step={s} />}
              {isNow && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-2">
                  <Markdown className="text-[13.5px] leading-relaxed [&_p]:text-fg-0">{s.say}</Markdown>
                  {s.kind === "search" && (
                    <div className="mt-2 space-y-0.5">
                      {s.hits?.length ? (
                        s.hits.slice(0, 8).map((h, k) => (
                          <div key={k} className="truncate font-mono text-[11px] text-fg-2">
                            <span className="text-amber">{h.path}:{h.line}</span> {h.text}
                          </div>
                        ))
                      ) : (
                        <div className="font-mono text-[11px] text-fg-3">no matches</div>
                      )}
                    </div>
                  )}
                </motion.div>
              )}
              {!isNow && !future && <div className="mt-0.5 line-clamp-1 text-[11.5px] text-fg-3">{plain(s.say)}</div>}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function You({ step }: { step: ReplayStep }) {
  if (step.you_at == null) {
    return <div className="mt-0.5 pl-5.5 text-[11px] text-fg-3">you {step.kind === "read" ? "never opened this file" : "didn't search for this"}</div>;
  }
  const slower = step.you_at - step.at > 120;
  return (
    <div className={clsx("mt-0.5 pl-5.5 text-[11px]", slower ? "text-amber/90" : "text-blue")}>
      you got here at {clock(step.you_at)}
    </div>
  );
}

function EndCard({ data, mentorName, onAgain, onClose }: { data: ReplayPayload; mentorName: string; onAgain: () => void; onClose: () => void }) {
  const steps = data.steps ?? [];
  // Where the time went: files the expert read that you reached much later, or never.
  const gaps = steps
    .filter((s) => s.kind === "read" && (s.you_at == null || s.you_at - s.at > 120))
    .filter((s, n, all) => all.findIndex((x) => x.path === s.path) === n)
    .slice(0, 3);
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="absolute inset-0 z-10 grid place-items-center bg-ink-0/85 backdrop-blur-md">
      <div className="w-[560px] max-w-[92%] rounded-3xl border border-line-strong bg-ink-1 p-8 shadow-2xl">
        <div className="text-[12px] font-semibold tracking-[0.12em] text-green uppercase">That's the whole path</div>
        <div className="mt-3 flex items-baseline gap-6">
          <div>
            <div className="font-mono text-[30px] text-fg-0 tabular-nums">{clock(data.expert_seconds ?? 0)}</div>
            <div className="text-[12px] text-fg-3">{mentorName}</div>
          </div>
          <div>
            <div className="font-mono text-[30px] text-fg-1 tabular-nums">{clock(data.your_seconds ?? 0)}</div>
            <div className="text-[12px] text-fg-3">you</div>
          </div>
        </div>
        {data.takeaway && <Markdown className="mt-5 text-[15px] leading-relaxed [&_p]:text-fg-0">{data.takeaway}</Markdown>}
        {gaps.length > 0 && (
          <div className="mt-5 border-t border-line pt-4">
            <div className="text-[12px] font-medium text-fg-1">Where the time went</div>
            <ul className="mt-2 space-y-1">
              {gaps.map((s) => (
                <li key={s.path} className="font-mono text-[12px] text-fg-2">
                  <span className="text-blue">{s.path}</span> — {mentorName} at {clock(s.at)},{" "}
                  {s.you_at == null ? "you never opened it" : `you at ${clock(s.you_at)}`}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-6 flex items-center gap-3">
          <Button tone="green" icon={<RotateCcw className="size-4" />} onClick={onAgain}>
            Watch again
          </Button>
          <Button ghost onClick={onClose}>
            Back
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
