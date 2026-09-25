import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { fileIcon } from "./Explorer";
import { useWB } from "./store";

// Cmd+P: fuzzy file finder. Supports `path:line`.

function score(query: string, path: string): number {
  const q = query.toLowerCase();
  const p = path.toLowerCase();
  const name = p.split("/").pop() ?? p;
  if (name.startsWith(q)) return 1000 - name.length;
  if (name.includes(q)) return 800 - name.length;
  if (p.includes(q)) return 600 - p.length;
  let qi = 0;
  let s = 0;
  let streak = 0;
  for (let i = 0; i < p.length && qi < q.length; i++) {
    if (p[i] === q[qi]) {
      qi++;
      streak++;
      s += 2 + streak;
    } else streak = 0;
  }
  return qi === q.length ? s : -1;
}

export default function QuickOpen() {
  const tree = useWB((s) => s.tree);
  const { set, openFile, log } = useWB.getState();
  const [query, setQuery] = useState("");
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => inputRef.current?.focus(), []);

  const [base, lineStr] = query.split(":");
  const results = useMemo(() => {
    const files = tree.filter((e) => e.type === "file").map((e) => e.path);
    if (!base.trim()) return files.slice(0, 40);
    return files
      .map((p) => ({ p, s: score(base.trim(), p) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 40)
      .map((x) => x.p);
  }, [tree, base]);

  const choose = (path: string) => {
    const line = Number(lineStr) || undefined;
    set({ quickOpen: false });
    log("quick_open", { query: base, path });
    void openFile(path, false, line, 1, line ? "flash" : undefined);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-center bg-black/40 pt-[12vh]" onMouseDown={() => set({ quickOpen: false })}>
      <div className="h-fit w-[560px] overflow-hidden rounded-xl border border-line-strong bg-ink-2 shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIdx(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") set({ quickOpen: false });
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setIdx((i) => Math.min(i + 1, results.length - 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setIdx((i) => Math.max(i - 1, 0));
            }
            if (e.key === "Enter" && results[idx]) choose(results[idx]);
          }}
          placeholder="Go to file…  (tip: name:42 jumps to a line)"
          className="w-full border-b border-line bg-transparent px-4 py-3 text-[14px] text-fg-0 outline-none placeholder:text-fg-3"
        />
        <div className="max-h-[50vh] overflow-y-auto py-1">
          {results.map((p, i) => {
            const name = p.split("/").pop() ?? p;
            const dir = p.slice(0, p.length - name.length).replace(/\/$/, "");
            return (
              <button
                key={p}
                onMouseEnter={() => setIdx(i)}
                onClick={() => choose(p)}
                className={clsx("flex w-full items-center gap-2 px-4 py-1.5 text-left", i === idx ? "bg-ink-4" : "")}
              >
                {fileIcon(name)}
                <span className="text-[13px] text-fg-0">{name}</span>
                <span className="truncate text-[12px] text-fg-3">{dir}</span>
              </button>
            );
          })}
          {!results.length && <div className="px-4 py-3 text-[13px] text-fg-2">No matching files</div>}
        </div>
      </div>
    </div>
  );
}
