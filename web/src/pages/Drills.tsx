import clsx from "clsx";
import { motion } from "motion/react";
import { ArrowRight, CheckCircle2, Timer, XCircle } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { REGION_COLORS } from "../components/HexMap";
import { Button, Card, Chip, Markdown, Spinner } from "../components/ui";
import { authHeaders } from "../lib/auth";

// Two-minute reps. Predict-the-output answers are the program's REAL output;
// spot-the-bug drills were verified to fail as written and pass when fixed.

interface Drill {
  id: number;
  kind: "predict" | "spot";
  title: string;
  code: string;
  question: string;
  concept: { id: string; name: string; region: string } | null;
}

interface Result {
  correct: boolean;
  answer?: string;
  bug_line?: number;
  fixed_line?: string;
  explanation: string;
  takeaway: string;
}

async function call<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: body ? "POST" : "GET",
    headers: { ...(body ? { "Content-Type": "application/json", "X-Coldstart": "1" } : {}), ...(await authHeaders()) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function useColorizedLines(code: string): string[] | null {
  const [lines, setLines] = useState<string[] | null>(null);
  useEffect(() => {
    let alive = true;
    setLines(null);
    import("../lib/monaco").then(async (m) => {
      const html = await m.colorize(code, "python");
      if (alive) setLines(html.split(/<br\s*\/?>/).slice(0, code.split("\n").length));
    });
    return () => {
      alive = false;
    };
  }, [code]);
  return lines;
}

export default function Drills() {
  const [drill, setDrill] = useState<Drill | null>(null);
  const [generating, setGenerating] = useState(false);
  const [week, setWeek] = useState(0);
  const [answer, setAnswer] = useState("");
  const [line, setLine] = useState<number | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const load = useCallback(async () => {
    const r = await call<{ drill: Drill | null; generating: boolean; stats: { week_answered: number } }>("/api/drills/next");
    setDrill(r.drill);
    setGenerating(r.generating);
    setWeek(r.stats.week_answered);
    setAnswer("");
    setLine(null);
    setResult(null);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll while the first batch is being written and verified.
  useEffect(() => {
    if (drill || !generating) return;
    const id = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(id);
  }, [drill, generating, load]);

  useEffect(() => {
    if (drill?.kind === "predict" && !result) inputRef.current?.focus();
  }, [drill, result]);

  const submit = async () => {
    if (!drill) return;
    const given = drill.kind === "spot" ? String(line ?? "") : answer;
    if (!given.trim()) return;
    setSubmitting(true);
    try {
      setResult(await call<Result>(`/api/drills/${drill.id}/answer`, { answer: given }));
      setWeek((w) => w + 1);
    } finally {
      setSubmitting(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" && result) {
        e.preventDefault();
        void load();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [result, load]);

  return (
    <div className="mx-auto max-w-[860px] px-6 py-10">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-[42px] leading-none text-fg-0">Drills</h1>
          <p className="mt-2 text-[14.5px] text-fg-1">Two-minute reps on the Python that bites. Every answer is checked by actually running the code.</p>
        </div>
        <span className="inline-flex items-center gap-1.5 text-[12.5px] text-fg-2">
          <Timer className="size-3.5" /> {week} this week
        </span>
      </div>

      {!drill ? (
        <Card className="mt-8 grid place-items-center p-12 text-center">
          <Spinner className="size-5" />
          <div className="mt-3 text-[14px] text-fg-1">Writing and verifying a fresh set of drills…</div>
          <div className="mt-1 text-[12.5px] text-fg-3">Each one is executed in the sandbox before you see it. About a minute.</div>
        </Card>
      ) : (
        <motion.div key={drill.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-8">
          <Card className="overflow-hidden">
            <div className="flex items-center gap-2 border-b border-line px-5 py-3">
              {drill.concept && (
                <Chip>
                  <span className="size-1.5 rounded-full" style={{ background: REGION_COLORS[drill.concept.region] }} />
                  {drill.concept.name}
                </Chip>
              )}
              <span className="text-[14px] font-medium text-fg-0">{drill.title}</span>
              <Chip tone={drill.kind === "predict" ? "blue" : "amber"} className="ml-auto">
                {drill.kind === "predict" ? "predict the output" : "spot the bug"}
              </Chip>
            </div>
            <CodeLines
              code={drill.code}
              selectable={drill.kind === "spot" && !result}
              selected={line}
              onSelect={setLine}
              correctLine={result?.bug_line}
            />
            <div className="border-t border-line px-5 py-4">
              <div className="text-[14px] text-fg-0">{drill.question}</div>
              {!result && drill.kind === "predict" && (
                <textarea
                  ref={inputRef}
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit();
                  }}
                  rows={Math.max(2, answer.split("\n").length)}
                  placeholder="Type the exact output (⌘↵ to check)"
                  className="mt-3 w-full resize-y rounded-lg border border-line-strong bg-ink-0 px-3 py-2 font-mono text-[13px] text-fg-0 outline-none placeholder:text-fg-3 focus:border-blue"
                />
              )}
              {!result && drill.kind === "spot" && (
                <div className="mt-2 text-[12.5px] text-fg-2">{line ? `Line ${line} selected.` : "Click the line you think is wrong."}</div>
              )}
              {!result && (
                <Button className="mt-3" tone="blue" loading={submitting} onClick={() => void submit()} disabled={drill.kind === "spot" ? !line : !answer.trim()}>
                  Check
                </Button>
              )}
            </div>
          </Card>

          {result && (
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-3">
              <div className={clsx("flex items-center gap-2 text-[15px] font-medium", result.correct ? "text-green" : "text-red")}>
                {result.correct ? <CheckCircle2 className="size-5" /> : <XCircle className="size-5" />}
                {result.correct ? "Right." : "Not quite."}
              </div>
              {drill.kind === "predict" && (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <div className="mb-1 text-[12px] text-fg-2">Actual output</div>
                    <pre className="rounded-lg border border-green/20 bg-green-dim/30 p-3 font-mono text-[12.5px] whitespace-pre-wrap text-fg-0">{result.answer}</pre>
                  </div>
                  {!result.correct && (
                    <div>
                      <div className="mb-1 text-[12px] text-fg-2">You said</div>
                      <pre className="rounded-lg border border-line bg-ink-1 p-3 font-mono text-[12.5px] whitespace-pre-wrap text-fg-1">{answer}</pre>
                    </div>
                  )}
                </div>
              )}
              {drill.kind === "spot" && result.fixed_line && (
                <div>
                  <div className="mb-1 text-[12px] text-fg-2">Line {result.bug_line}, fixed</div>
                  <pre className="rounded-lg border border-green/20 bg-green-dim/30 p-3 font-mono text-[12.5px] whitespace-pre-wrap text-fg-0">{result.fixed_line}</pre>
                </div>
              )}
              <Markdown className="text-[14px]">{result.explanation}</Markdown>
              {result.takeaway && (
                <div className="rounded-xl border border-teal/20 bg-teal-dim/30 px-4 py-3 text-[14px] text-fg-0">{result.takeaway}</div>
              )}
              <Button tone="blue" icon={<ArrowRight className="size-4" />} onClick={() => void load()}>
                Next drill <span className="text-[11px] opacity-70">↵</span>
              </Button>
            </motion.div>
          )}
        </motion.div>
      )}
    </div>
  );
}

function CodeLines({ code, selectable, selected, onSelect, correctLine }: { code: string; selectable: boolean; selected: number | null; onSelect: (n: number) => void; correctLine?: number }) {
  const html = useColorizedLines(code);
  const raw = code.split("\n");
  return (
    <div className="overflow-x-auto bg-ink-1 py-3 font-mono text-[13px] leading-[1.7]">
      {raw.map((text, i) => {
        const n = i + 1;
        const isSel = selected === n;
        const isBug = correctLine === n;
        return (
          <div
            key={n}
            onClick={() => selectable && onSelect(n)}
            className={clsx(
              "flex pr-4",
              selectable && "cursor-pointer hover:bg-ink-3",
              isSel && !correctLine && "bg-blue-dim",
              isBug && "bg-amber-dim",
              correctLine && isSel && !isBug && "bg-red-dim",
            )}
          >
            <span className="w-12 shrink-0 pr-4 text-right text-fg-3 select-none">{n}</span>
            {html ? <span className="whitespace-pre" dangerouslySetInnerHTML={{ __html: html[i] ?? "" }} /> : <span className="whitespace-pre text-fg-1">{text}</span>}
          </div>
        );
      })}
    </div>
  );
}
