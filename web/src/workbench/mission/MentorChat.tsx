import clsx from "clsx";
import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Avatar, Markdown } from "../../components/ui";
import { api, streamChat } from "../../lib/api";
import type { ChatMessage } from "../../lib/types";
import { useWB } from "../store";

const STARTERS: Record<string, string[]> = {
  recon: ["Where would you start in this codebase?", "What's the core data model here?", "Explain the code I've selected"],
  incident: ["Help me turn this report into a hypothesis", "How do I reproduce this in the terminal?", "Explain the code I've selected"],
  feature: ["Where does this feature belong?", "Is there existing code I should mirror?", "Review my approach so far"],
};

export default function MentorChat({ taskId, kind, mentorName }: { taskId: string; kind: string; mentorName: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Check-ins from the coach land in this conversation too.
  const nudgeCount = useWB((s) => (s.live.taskId === taskId ? s.live.nudges.length : 0));
  useEffect(() => {
    if (streaming) return;
    api.chatHistory(taskId).then((r) => setMessages(r.messages)).catch(() => {});
  }, [taskId, nudgeCount]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || streaming) return;
    const { active, editor } = useWB.getState();
    const selection = editor?.getModel() && editor.getSelection() ? editor.getModel()!.getValueInRange(editor.getSelection()!) : "";
    const context = {
      file: active?.path,
      line: editor?.getPosition()?.lineNumber,
      selection: selection.slice(0, 2000),
    };
    setInput("");
    setError(null);
    setMessages((m) => [...m, { role: "user", content: message }, { role: "assistant", content: "" }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat(
        taskId,
        message,
        context,
        (delta) =>
          setMessages((m) => {
            const next = [...m];
            next[next.length - 1] = { role: "assistant", content: next[next.length - 1].content + delta };
            return next;
          }),
        controller.signal,
      );
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 && (
          <div className="rounded-xl border border-teal/15 bg-teal-dim/30 p-4">
            <div className="flex items-center gap-2">
              <Avatar name={mentorName} size={26} />
              <div className="text-[13px] text-fg-0">
                <span className="font-semibold">{mentorName}</span> <span className="text-fg-2">· senior engineer, pairing with you</span>
              </div>
            </div>
            <p className="mt-2 text-[12.5px] leading-relaxed text-fg-1">
              I know this codebase and what's wrong with it — but I'll help you find it rather than hand it over. Ask me about Python, the code, tools, or your theory. Select code in the editor and I'll see it.
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {(STARTERS[kind] ?? STARTERS.incident).map((s) => (
                <button key={s} onClick={() => void send(s)} className="rounded-full border border-teal/25 px-2.5 py-1 text-[12px] text-teal hover:bg-teal-dim">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="ml-8 rounded-xl rounded-br-sm bg-ink-3 px-3.5 py-2.5 text-[13px] whitespace-pre-wrap text-fg-0">
              {m.content}
            </div>
          ) : m.role === "nudge" ? (
            <div key={i} className="flex gap-2.5">
              <Avatar name={mentorName} size={24} />
              <div className="min-w-0 flex-1 border-l-2 border-teal/50 pl-2.5">
                <div className="text-[10.5px] font-semibold tracking-[0.08em] text-teal uppercase">checked in</div>
                <Markdown className="mt-0.5 text-[13px]">{m.content}</Markdown>
              </div>
            </div>
          ) : (
            <div key={i} className="flex gap-2.5">
              <Avatar name={mentorName} size={24} />
              <div className="min-w-0 flex-1">
                {m.content ? <Markdown className="text-[13px]">{m.content}</Markdown> : <span className="inline-block size-2 animate-breathe rounded-full bg-teal" />}
              </div>
            </div>
          ),
        )}
        {error && <div className="text-[12px] text-red">{error}</div>}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-line p-3">
        <div className="flex items-end gap-2 rounded-xl border border-line-strong bg-ink-0 p-2 focus-within:border-teal/60">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send(input);
              }
            }}
            rows={Math.min(6, Math.max(1, input.split("\n").length))}
            placeholder={`Ask ${mentorName}…`}
            className="cs-bare max-h-40 min-h-[22px] flex-1 resize-none bg-transparent px-1 text-[13px] text-fg-0 outline-none placeholder:text-fg-3"
          />
          <button
            onClick={() => (streaming ? abortRef.current?.abort() : void send(input))}
            className={clsx("grid size-7 shrink-0 place-items-center rounded-lg", streaming ? "bg-ink-4 text-fg-1" : input.trim() ? "bg-teal text-ink-0" : "bg-ink-3 text-fg-3")}
          >
            {streaming ? <Square className="size-3" /> : <ArrowUp className="size-3.5" />}
          </button>
        </div>
      </div>
    </div>
  );
}
