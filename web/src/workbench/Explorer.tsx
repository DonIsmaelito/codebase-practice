import clsx from "clsx";
import { ChevronRight, FileCode2, FileJson, FileText, FlaskConical, Folder, FolderOpen, FilePlus2, FolderPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { useShallow } from "zustand/react/shallow";
import { useWB } from "./store";

interface Node {
  name: string;
  path: string;
  type: "file" | "dir";
  children: Node[];
}

function buildTree(entries: { path: string; type: "file" | "dir" }[]): Node[] {
  const root: Node = { name: "", path: "", type: "dir", children: [] };
  const dirs = new Map<string, Node>([["", root]]);
  const sorted = [...entries].sort((a, b) => a.path.localeCompare(b.path));
  for (const e of sorted) {
    const parts = e.path.split("/");
    const parentPath = parts.slice(0, -1).join("/");
    let parent = dirs.get(parentPath);
    if (!parent) {
      // create missing intermediate dirs
      let acc = "";
      parent = root;
      for (const part of parts.slice(0, -1)) {
        acc = acc ? `${acc}/${part}` : part;
        let d = dirs.get(acc);
        if (!d) {
          d = { name: part, path: acc, type: "dir", children: [] };
          dirs.set(acc, d);
          parent.children.push(d);
        }
        parent = d;
      }
    }
    const node: Node = { name: parts[parts.length - 1], path: e.path, type: e.type, children: [] };
    if (e.type === "dir") {
      if (dirs.has(e.path)) continue;
      dirs.set(e.path, node);
    }
    parent.children.push(node);
  }
  const sortRec = (n: Node) => {
    n.children.sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === "dir" ? -1 : 1));
    n.children.forEach(sortRec);
  };
  sortRec(root);
  return root.children;
}

export function fileIcon(name: string, className = "size-3.5") {
  if (name.startsWith("test_") || name === "conftest.py") return <FlaskConical className={clsx(className, "text-green/80")} />;
  if (name.endsWith(".py")) return <FileCode2 className={clsx(className, "text-blue/80")} />;
  if (name.endsWith(".json") || name.endsWith(".toml") || name.endsWith(".yaml") || name.endsWith(".yml")) return <FileJson className={clsx(className, "text-amber/80")} />;
  return <FileText className={clsx(className, "text-fg-2")} />;
}

export default function Explorer() {
  const { tree, active, changed, eid, data } = useWB(
    useShallow((s) => ({ tree: s.tree, active: s.active, changed: s.changed, eid: s.eid, data: s.data })),
  );
  const { openFile, refreshTree } = useWB.getState();
  const nodes = useMemo(() => buildTree(tree), [tree]);
  const pkg = data?.case.repo.package;
  const [open, setOpen] = useState<Set<string>>(() => new Set(pkg ? [pkg] : []));
  const [creating, setCreating] = useState<{ kind: "file" | "dir"; dir: string } | null>(null);
  const [name, setName] = useState("");

  const toggle = (path: string) => {
    const next = new Set(open);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setOpen(next);
  };

  const create = async () => {
    if (!eid || !creating || !name.trim()) return setCreating(null);
    const path = creating.dir ? `${creating.dir}/${name.trim()}` : name.trim();
    try {
      await api.fs(eid, "create", path, { kind: creating.kind });
      await refreshTree();
      if (creating.kind === "file") void openFile(path);
    } finally {
      setCreating(null);
      setName("");
    }
  };

  const render = (n: Node, depth: number): React.ReactNode => {
    const pad = 10 + depth * 12;
    if (n.type === "dir") {
      const isOpen = open.has(n.path);
      const hasChange = [...changed].some((c) => c.startsWith(n.path + "/"));
      return (
        <div key={n.path}>
          <button
            className="flex w-full items-center gap-1.5 py-[3px] pr-2 text-left text-[13px] text-fg-1 hover:bg-ink-3"
            style={{ paddingLeft: pad }}
            onClick={() => toggle(n.path)}
          >
            <ChevronRight className={clsx("size-3 shrink-0 text-fg-3 transition-transform", isOpen && "rotate-90")} />
            {isOpen ? <FolderOpen className="size-3.5 shrink-0 text-fg-2" /> : <Folder className="size-3.5 shrink-0 text-fg-2" />}
            <span className="truncate">{n.name}</span>
            {hasChange && !isOpen && <span className="ml-auto size-1.5 rounded-full bg-amber" />}
          </button>
          {isOpen && n.children.map((c) => render(c, depth + 1))}
        </div>
      );
    }
    const isActive = active && !active.external && active.path === n.path;
    return (
      <button
        key={n.path}
        className={clsx(
          "flex w-full items-center gap-1.5 py-[3px] pr-2 text-left text-[13px]",
          isActive ? "bg-ink-4 text-fg-0" : "text-fg-1 hover:bg-ink-3",
        )}
        style={{ paddingLeft: pad + 15 }}
        onClick={() => void openFile(n.path)}
        title={n.path}
      >
        {fileIcon(n.name)}
        <span className={clsx("truncate", changed.has(n.path) && "text-amber")}>{n.name}</span>
        {changed.has(n.path) && <span className="ml-auto font-mono text-[10px] text-amber">M</span>}
      </button>
    );
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-9 shrink-0 items-center justify-between px-3">
        <span className="text-[11px] font-semibold tracking-[0.08em] text-fg-2 uppercase">{data?.case.repo.name ?? "Explorer"}</span>
        <div className="flex gap-0.5">
          <button className="rounded p-1 text-fg-2 hover:bg-ink-3 hover:text-fg-0" title="New file" onClick={() => setCreating({ kind: "file", dir: active && !active.external ? active.path.split("/").slice(0, -1).join("/") : "" })}>
            <FilePlus2 className="size-3.5" />
          </button>
          <button className="rounded p-1 text-fg-2 hover:bg-ink-3 hover:text-fg-0" title="New folder" onClick={() => setCreating({ kind: "dir", dir: "" })}>
            <FolderPlus className="size-3.5" />
          </button>
        </div>
      </div>
      {creating && (
        <div className="px-3 pb-2">
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void create();
              if (e.key === "Escape") setCreating(null);
            }}
            onBlur={() => void create()}
            placeholder={`${creating.dir ? creating.dir + "/" : ""}new_${creating.kind === "file" ? "module.py" : "folder"}`}
            className="w-full rounded-md border border-line-strong bg-ink-0 px-2 py-1 font-mono text-[12px] text-fg-0 outline-none focus:border-blue"
          />
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto pb-4">{nodes.map((n) => render(n, 0))}</div>
    </div>
  );
}
