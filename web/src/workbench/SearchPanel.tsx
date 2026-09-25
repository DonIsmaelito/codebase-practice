import clsx from "clsx";
import { CaseSensitive, Regex, WholeWord } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { SearchResult } from "../lib/types";
import { fileIcon } from "./Explorer";
import { useWB } from "./store";

export default function SearchPanel() {
  const eid = useWB((s) => s.eid);
  const { openFile, log } = useWB.getState();
  const [query, setQuery] = useState("");
  const [opts, setOpts] = useState({ regex: false, case: false, word: false });
  const [res, setRes] = useState<SearchResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const lastLogged = useRef("");

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!eid) return;
    if (!query.trim()) {
      setRes(null);
      return;
    }
    const id = window.setTimeout(async () => {
      const r = await api.search(eid, { q: query, ...opts });
      setRes(r);
      if (query.length > 2 && query !== lastLogged.current) {
        lastLogged.current = query;
        log("search", { query, total: r.total });
      }
    }, 220);
    return () => window.clearTimeout(id);
  }, [query, opts, eid, log]);

  const toggle = (k: keyof typeof opts) => setOpts({ ...opts, [k]: !opts[k] });

  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-3 pb-2">
        <div className="flex items-center rounded-md border border-line-strong bg-ink-0 focus-within:border-blue">
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the codebase"
            className="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-[12.5px] text-fg-0 outline-none placeholder:text-fg-3"
          />
          {(
            [
              ["case", CaseSensitive, "Match case"],
              ["word", WholeWord, "Whole word"],
              ["regex", Regex, "Regular expression"],
            ] as const
          ).map(([k, Icon, title]) => (
            <button key={k} title={title} onClick={() => toggle(k)} className={clsx("mr-0.5 rounded p-1", opts[k] ? "bg-blue-dim text-blue" : "text-fg-3 hover:text-fg-1")}>
              <Icon className="size-3.5" />
            </button>
          ))}
        </div>
        {res && (
          <div className="mt-2 text-[11.5px] text-fg-2">
            {res.error ?? `${res.total}${res.truncated ? "+" : ""} results in ${res.results.length} files`}
          </div>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto pb-4">
        {res?.results.map((f) => (
          <div key={f.path} className="mb-1">
            <div className="flex items-center gap-1.5 px-3 py-1 text-[12.5px] text-fg-1">
              {fileIcon(f.path.split("/").pop() ?? "")}
              <span className="truncate">{f.path}</span>
              <span className="ml-auto rounded bg-ink-3 px-1.5 text-[10.5px] text-fg-2">{f.matches.length}</span>
            </div>
            {f.matches.map((m, i) => {
              const start = Math.max(0, m.column - 1 - 30);
              const pre = m.text.slice(start, m.column - 1).trimStart();
              const hit = m.text.slice(m.column - 1, m.column - 1 + m.length);
              const post = m.text.slice(m.column - 1 + m.length, m.column - 1 + m.length + 80);
              return (
                <button
                  key={i}
                  onClick={() => void openFile(f.path, false, m.line, m.column, "flash")}
                  className="flex w-full items-baseline gap-2 py-[2px] pr-2 pl-8 text-left font-mono text-[11.5px] text-fg-2 hover:bg-ink-3"
                >
                  <span className="w-7 shrink-0 text-right text-fg-3">{m.line}</span>
                  <span className="truncate">
                    {pre}
                    <span className="rounded-sm bg-amber/25 text-fg-0">{hit}</span>
                    {post}
                  </span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
