import clsx from "clsx";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, CheckCircle2, FileText, Hash, Mail, Radio, RotateCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Avatar, Markdown } from "../../components/ui";
import { channelLabel } from "../../lib/format";
import type { Message, Report, ThreadMessage } from "../../lib/types";

const icons: Record<string, typeof Hash> = { slack: Hash, email: Mail, jira: FileText, pager: Radio };

// Shown until you've messaged a thread once: the questions experts ask first.
const STARTERS = ["Who's affected — and who isn't?", "When did this start? Anything change around then?", "Can you send me the exact input?"];
const STARTERS_KEY = "cs-thread-used";

export interface LiveThread {
  messages: ThreadMessage[];
  typing: string | null;
  error: string | null;
  startedAt: number | null;
  onSend?: (text: string) => Promise<void>;
  onRetry?: () => void;
}

/** A report thread. On first view the report arrives message by message, like the real
 *  thing; after that the thread stays live — the team answers and posts as you work. */
export default function Thread({ report, animate, onAllShown, live }: { report: Report; animate: boolean; onAllShown?: () => void; live?: LiveThread }) {
  const [shown, setShown] = useState(animate ? 0 : report.messages.length);
  const Icon = icons[report.channel] ?? Hash;
  const reportDone = shown >= report.messages.length;

  useEffect(() => {
    if (shown >= report.messages.length) {
      onAllShown?.();
      return;
    }
    const delay = shown === 0 ? 500 : Math.min(2200, 700 + report.messages[shown - 1].body.length * 4);
    const id = window.setTimeout(() => setShown((s) => s + 1), delay);
    return () => window.clearTimeout(id);
  }, [shown, report.messages, onAllShown]);

  const lastTime = [...report.messages].reverse().find((m) => m.time)?.time;

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-ink-2/60">
      <div className="flex items-center gap-2 border-b border-line px-3.5 py-2.5">
        <Icon className="size-3.5 text-amber" />
        <span className="truncate text-[13px] font-medium text-fg-0">{report.title}</span>
        <span className="ml-auto text-[11px] text-fg-3">{channelLabel[report.channel] ?? report.channel}</span>
      </div>
      <div className="space-y-4 px-3.5 py-3.5">
        <AnimatePresence initial={false}>
          {report.messages.slice(0, shown).map((m, i) => (
            <motion.div key={`r${i}`} initial={animate ? { opacity: 0, y: 6 } : false} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
              <Post from={m.from} role={m.role} time={m.time} body={m.body} />
            </motion.div>
          ))}
          {reportDone &&
            live?.messages.map((m) => (
              <motion.div key={m.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
                <Post
                  from={m.author}
                  role={m.kind === "learner" ? "" : m.author_role ?? ""}
                  time={liveTime(lastTime, live.startedAt, m.ts)}
                  body={m.body}
                  you={m.kind === "learner"}
                  resolved={m.kind === "resolution"}
                />
              </motion.div>
            ))}
        </AnimatePresence>
        {!reportDone && <Typing name={report.messages[shown]?.from} />}
        {reportDone && live?.typing != null && <Typing name={live.typing || undefined} />}
        {reportDone && live?.error && (
          <div className="flex items-start gap-2 pl-9 text-[12px] text-red">
            <span className="min-w-0 flex-1">Your message didn't get an answer: {live.error.replace(/^\w+Error: /, "")}</span>
            {live.onRetry && (
              <button onClick={live.onRetry} className="inline-flex shrink-0 items-center gap-1 text-fg-1 hover:text-fg-0">
                <RotateCw className="size-3" /> retry
              </button>
            )}
          </div>
        )}
      </div>
      {reportDone && report.ask && (
        <div className="border-t border-line bg-amber-dim/40 px-3.5 py-2 text-[12.5px] text-amber">
          <span className="font-semibold">The ask:</span> {report.ask}
        </div>
      )}
      {reportDone && live?.onSend && <Composer onSend={live.onSend} names={peopleIn(report.messages)} />}
    </div>
  );
}

function Post({ from, role, time, body, you, resolved }: { from: string; role?: string; time?: string; body: string; you?: boolean; resolved?: boolean }) {
  return (
    <div className={clsx("flex gap-2.5", resolved && "-mx-1.5 rounded-lg border-l-2 border-green bg-green-dim/20 px-1.5 py-1.5")}>
      {you ? (
        <div className="grid size-[26px] shrink-0 place-items-center rounded-full border border-blue/40 bg-blue-dim text-[9.5px] font-semibold text-blue">you</div>
      ) : (
        <Avatar name={from} size={26} />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className={clsx("text-[13px] font-semibold", you ? "text-blue" : "text-fg-0")}>{from}</span>
          {role && <span className="truncate text-[11.5px] text-fg-2">{role}</span>}
          {resolved && <CheckCircle2 className="size-3.5 shrink-0 translate-y-0.5 text-green" />}
          {time && <span className="ml-auto shrink-0 text-[11px] text-fg-3">{time}</span>}
        </div>
        {you ? (
          <div className="mt-0.5 text-[13px] whitespace-pre-wrap text-fg-1">{body}</div>
        ) : (
          <Markdown className="mt-0.5 text-[13px]">{body}</Markdown>
        )}
      </div>
    </div>
  );
}

function Typing({ name }: { name?: string }) {
  return (
    <div className="flex items-center gap-2 pl-9 text-[11.5px] text-fg-3">
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span key={i} className="size-1 animate-breathe rounded-full bg-fg-3" style={{ animationDelay: `${i * 0.2}s` }} />
        ))}
      </span>
      {name ? `${name} is typing…` : "typing…"}
    </div>
  );
}

function Composer({ onSend, names }: { onSend: (text: string) => Promise<void>; names: string[] }) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [showStarters, setShowStarters] = useState(() => {
    try {
      return !localStorage.getItem(STARTERS_KEY);
    } catch {
      return false;
    }
  });

  const send = async (value: string) => {
    const body = value.trim();
    if (!body || sending) return;
    setSending(true);
    setError(null);
    try {
      await onSend(body);
      setText("");
      setShowStarters(false);
      try {
        localStorage.setItem(STARTERS_KEY, "1");
      } catch {
        /* private mode */
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="border-t border-line bg-ink-1/60 px-3 py-2.5">
      {showStarters && (
        <div className="mb-2">
          <div className="mb-1.5 text-[11px] text-fg-3">The team only knows what you ask. Experts start with:</div>
          <div className="flex flex-wrap gap-1.5">
            {STARTERS.map((s) => (
              <button
                key={s}
                onClick={() => {
                  setText(s);
                  input.current?.focus();
                }}
                className="rounded-full border border-amber/25 px-2.5 py-0.5 text-[11.5px] text-amber hover:bg-amber-dim"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="flex items-end gap-2 rounded-lg border border-line-strong bg-ink-0 p-1.5 focus-within:border-amber/60">
        <textarea
          ref={input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send(text);
            }
          }}
          rows={Math.min(5, Math.max(1, text.split("\n").length))}
          placeholder={`Reply to ${names.slice(0, 2).join(", ") || "the thread"}…`}
          className="cs-bare max-h-32 min-h-[22px] flex-1 resize-none bg-transparent px-1.5 py-0.5 text-[13px] text-fg-0 outline-none placeholder:text-fg-3"
        />
        <button
          onClick={() => void send(text)}
          disabled={sending}
          className={clsx("grid size-7 shrink-0 place-items-center rounded-md", text.trim() ? "bg-amber text-ink-0" : "bg-ink-3 text-fg-3")}
          title="Send (Enter)"
        >
          <ArrowUp className="size-3.5" />
        </button>
      </div>
      {error && <div className="mt-1.5 text-[11.5px] text-red">{error}</div>}
    </div>
  );
}

function peopleIn(messages: Message[]): string[] {
  return [...new Set(messages.map((m) => m.from.split(" ")[0]))];
}

/** Thread clock: the report's last timestamp plus real minutes since you picked it up. */
function liveTime(reportTime: string | undefined, startedAt: number | null, ts: number): string {
  const minutes = startedAt ? Math.max(0, Math.round((ts - startedAt) / 60)) : 0;
  const m = reportTime?.match(/(\d{1,2}):(\d{2})/);
  if (!m) return minutes ? `+${minutes}m` : "now";
  const total = Number(m[1]) * 60 + Number(m[2]) + minutes;
  const hh = Math.floor(total / 60) % 24;
  return reportTime!.replace(m[0], `${String(hh).padStart(m[1].length, "0")}:${String(total % 60).padStart(2, "0")}`);
}
