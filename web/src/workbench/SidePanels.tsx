import clsx from "clsx";
import { Box, FunctionSquare, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { EmptyState } from "../components/ui";
import { api } from "../lib/api";
import type { Change } from "../lib/types";
import { fileIcon } from "./Explorer";
import { useShallow } from "zustand/react/shallow";
import { useWB } from "./store";

export function ChangesPanel() {
  const { eid, tree, diffView } = useWB(useShallow((s) => ({ eid: s.eid, tree: s.tree, diffView: s.diffView })));
  const { set, refreshTree, openFile } = useWB.getState();
  const [changes, setChanges] = useState<Change[]>([]);

  useEffect(() => {
    if (eid) api.changes(eid).then((r) => setChanges(r.changes));
  }, [eid, tree]);

  const revert = async (path: string) => {
    if (!eid || !confirm(`Revert ${path} to how it was when this task started?`)) return;
    await api.revert(eid, path);
    const { getModel } = await import("../lib/monaco");
    const model = getModel(path);
    if (model) {
      try {
        const { content } = await api.readFile(eid, path);
        model.setValue(content);
      } catch {
        model.dispose();
      }
    }
    await refreshTree();
  };

  if (!changes.length) {
    return <EmptyState title="No changes yet">Files you edit during this task show up here, with a diff against where you started.</EmptyState>;
  }
  return (
    <div className="py-2">
      <div className="px-3 pb-2 text-[11px] font-semibold tracking-[0.08em] text-fg-2 uppercase">Your changes this task</div>
      {changes.map((c) => (
        <div key={c.path} className={clsx("group flex items-center gap-1.5 px-3 py-1 text-[12.5px]", diffView === c.path ? "bg-ink-4" : "hover:bg-ink-3")}>
          <button
            className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
            onClick={() => {
              if (c.status === "deleted") return;
              void openFile(c.path).then(() => set({ diffView: c.path }));
            }}
          >
            {fileIcon(c.path.split("/").pop() ?? "")}
            <span className="truncate text-fg-1">{c.path}</span>
          </button>
          <span className={clsx("font-mono text-[10.5px]", c.status === "added" ? "text-green" : c.status === "deleted" ? "text-red" : "text-amber")}>
            {c.status[0].toUpperCase()}
          </span>
          <button className="hidden rounded p-0.5 text-fg-3 group-hover:block hover:text-fg-0" title="Revert file" onClick={() => void revert(c.path)}>
            <RotateCcw className="size-3" />
          </button>
        </div>
      ))}
    </div>
  );
}

export function OutlinePanel() {
  const { eid, active } = useWB(useShallow((s) => ({ eid: s.eid, active: s.active })));
  const { openFile } = useWB.getState();
  const [syms, setSyms] = useState<{ name: string; type: string; line: number; column: number; parent: string | null }[]>([]);

  useEffect(() => {
    if (!eid || !active || active.external || !active.path.endsWith(".py")) {
      setSyms([]);
      return;
    }
    api.symbols(eid, active.path).then(setSyms).catch(() => setSyms([]));
  }, [eid, active]);

  if (!active || active.external) return <EmptyState title="No outline">Open a Python file to see its classes and functions.</EmptyState>;
  return (
    <div className="py-2">
      <div className="truncate px-3 pb-2 text-[11px] font-semibold tracking-[0.08em] text-fg-2 uppercase">{active.path.split("/").pop()}</div>
      {syms.map((s, i) => (
        <button
          key={i}
          onClick={() => void openFile(active.path, false, s.line, s.column, "flash")}
          className="flex w-full items-center gap-1.5 py-[3px] pr-2 text-left text-[12.5px] text-fg-1 hover:bg-ink-3"
          style={{ paddingLeft: s.parent ? 28 : 12 }}
        >
          {s.type === "class" ? <Box className="size-3.5 text-amber/80" /> : <FunctionSquare className="size-3.5 text-violet/80" />}
          <span className="truncate font-mono text-[12px]">{s.name}</span>
          <span className="ml-auto text-[10.5px] text-fg-3">{s.line}</span>
        </button>
      ))}
    </div>
  );
}
