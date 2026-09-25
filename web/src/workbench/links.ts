// Turn file references in tracebacks/pytest output into workspace paths, so
// `File "/…/repo/shop/cart.py", line 42` or `shop/cart.py:42` become clickable.

export const FILE_REF = /(?:File ")?((?:\/[^\s"':]+\/)?[\w.\-/]+\.py)(?:", line (\d+)|:(\d+))/g;

export function toWorkspacePath(raw: string, known: Set<string>): string | null {
  let p = raw;
  const repoIdx = p.lastIndexOf("/repo/");
  if (repoIdx !== -1) p = p.slice(repoIdx + "/repo/".length);
  const scratch = p.match(/\/scratch\/[^/]+\/(.+)$/);
  if (scratch) p = scratch[1];
  p = p.replace(/^\.\//, "");
  if (known.has(p)) return p;
  // Try trailing segments (absolute paths from elsewhere).
  const parts = p.split("/");
  for (let i = 1; i < parts.length; i++) {
    const tail = parts.slice(i).join("/");
    if (known.has(tail)) return tail;
  }
  return null;
}

export interface FileRef {
  start: number;
  end: number;
  path: string;
  line: number;
}

export function findRefs(text: string, known: Set<string>): FileRef[] {
  const out: FileRef[] = [];
  for (const m of text.matchAll(FILE_REF)) {
    const path = toWorkspacePath(m[1], known);
    if (!path) continue;
    const line = Number(m[2] ?? m[3]);
    out.push({ start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, path, line });
  }
  return out;
}
