import { create } from "zustand";
import { api } from "../lib/api";
import { createModel, getModel, type monaco } from "../lib/monaco";
import type { EngagementPayload, Task, TaskKind, TestReport, TreeEntry } from "../lib/types";

export interface Tab {
  path: string;
  external: boolean;
}

type SideView = "files" | "search" | "changes" | "outline";
type BottomTab = "terminal" | "tests";
type RightTab = "brief" | "mentor" | "notes";

interface Reveal {
  path: string;
  external: boolean;
  line: number;
  column?: number;
  highlight?: "tour" | "flash";
  endLine?: number;
}

interface WorkbenchState {
  eid: string | null;
  data: EngagementPayload | null;
  tree: TreeEntry[];
  changed: Set<string>;
  tabs: Tab[];
  active: Tab | null;
  dirty: Set<string>;
  reveal: Reveal | null;
  editor: monaco.editor.IStandaloneCodeEditor | null;
  side: SideView;
  sideOpen: boolean;
  bottomOpen: boolean;
  bottomTab: BottomTab;
  rightTab: RightTab;
  testReport: TestReport | null;
  testsRunning: boolean;
  quickOpen: boolean;
  diffView: string | null; // path shown in diff mode
  codeHidden: boolean; // closed-book recon: code is hidden while answering
  editedOnce: Set<string>;
  queue: { kind: string; data?: unknown; ts: number }[];

  load: (eid: string) => Promise<void>;
  refresh: () => Promise<void>;
  setData: (data: EngagementPayload) => void;
  refreshTree: () => Promise<void>;
  openFile: (path: string, external?: boolean, line?: number, column?: number, highlight?: Reveal["highlight"], endLine?: number) => Promise<void>;
  closeTab: (tab: Tab) => void;
  markDirty: (path: string) => void;
  save: (path: string) => Promise<void>;
  saveAll: () => Promise<void>;
  setEditor: (e: monaco.editor.IStandaloneCodeEditor | null) => void;
  consumeReveal: () => Reveal | null;
  set: (patch: Partial<WorkbenchState>) => void;
  log: (kind: string, data?: Record<string, unknown>) => void;
  flush: () => Promise<void>;
  runTests: (targets?: string[]) => Promise<TestReport | null>;
  activeTask: () => Task | null;
  beginTask: (kind: TaskKind) => Promise<void>;
  reset: () => void;
}

const initial = {
  eid: null,
  data: null,
  tree: [] as TreeEntry[],
  changed: new Set<string>(),
  tabs: [] as Tab[],
  active: null,
  dirty: new Set<string>(),
  reveal: null,
  editor: null,
  side: "files" as SideView,
  sideOpen: true,
  bottomOpen: true,
  bottomTab: "terminal" as BottomTab,
  rightTab: "brief" as RightTab,
  testReport: null,
  testsRunning: false,
  quickOpen: false,
  diffView: null,
  codeHidden: false,
  editedOnce: new Set<string>(),
  queue: [] as { kind: string; data?: unknown; ts: number }[],
};

const saveTimers = new Map<string, number>();

export const useWB = create<WorkbenchState>((set, get) => ({
  ...initial,

  async load(eid) {
    const [data, tree] = await Promise.all([api.engagement(eid), api.tree(eid)]);
    set({ eid, data, tree: tree.entries, changed: new Set(tree.changed) });
  },

  async refresh() {
    const { eid } = get();
    if (!eid) return;
    const data = await api.engagement(eid);
    set({ data });
  },

  setData(data) {
    set({ data });
  },

  async refreshTree() {
    const { eid } = get();
    if (!eid) return;
    const tree = await api.tree(eid);
    set({ tree: tree.entries, changed: new Set(tree.changed) });
  },

  async openFile(path, external = false, line, column, highlight, endLine) {
    const { eid, tabs } = get();
    if (!eid) return;
    let model = getModel(path, external);
    if (!model) {
      try {
        const { content } = external ? await api.external(path) : await api.readFile(eid, path);
        model = createModel(path, content, external);
      } catch {
        return;
      }
    }
    const tab = { path, external };
    const exists = tabs.some((t) => t.path === path && t.external === external);
    set({
      tabs: exists ? tabs : [...tabs, tab],
      active: tab,
      diffView: null,
      reveal: line ? { path, external, line, column, highlight, endLine } : null,
    });
    get().log("open_file", { path, external });
  },

  closeTab(tab) {
    const { tabs, active } = get();
    const idx = tabs.findIndex((t) => t.path === tab.path && t.external === tab.external);
    const next = tabs.filter((_, i) => i !== idx);
    let nextActive = active;
    if (active && active.path === tab.path && active.external === tab.external) {
      nextActive = next[Math.min(idx, next.length - 1)] ?? null;
    }
    if (!tab.external && get().dirty.has(tab.path)) void get().save(tab.path);
    set({ tabs: next, active: nextActive });
  },

  markDirty(path) {
    const dirty = new Set(get().dirty);
    dirty.add(path);
    set({ dirty });
    if (!get().editedOnce.has(path)) {
      const edited = new Set(get().editedOnce);
      edited.add(path);
      set({ editedOnce: edited });
      get().log("edit", { path });
    }
    // Autosave shortly after typing stops.
    window.clearTimeout(saveTimers.get(path));
    saveTimers.set(path, window.setTimeout(() => void get().save(path), 700));
  },

  async save(path) {
    const { eid } = get();
    const model = getModel(path, false);
    if (!eid || !model) return;
    window.clearTimeout(saveTimers.get(path));
    await api.writeFile(eid, path, model.getValue());
    const dirty = new Set(get().dirty);
    dirty.delete(path);
    set({ dirty });
    void get().refreshTree();
  },

  async saveAll() {
    await Promise.all([...get().dirty].map((p) => get().save(p)));
  },

  setEditor(editor) {
    set({ editor });
  },

  consumeReveal() {
    const r = get().reveal;
    if (r) set({ reveal: null });
    return r;
  },

  set(patch) {
    set(patch as Partial<WorkbenchState>);
  },

  log(kind, data = {}) {
    set({ queue: [...get().queue, { kind, data, ts: Date.now() / 1000 }] });
  },

  async flush() {
    const { eid, queue } = get();
    if (!eid || !queue.length) return;
    set({ queue: [] });
    const task = get().activeTask();
    try {
      await api.events(eid, task?.id ?? null, queue);
    } catch {
      set({ queue: [...queue, ...get().queue] });
    }
  },

  async runTests(targets) {
    const { eid } = get();
    if (!eid) return null;
    await get().saveAll();
    set({ testsRunning: true, bottomOpen: true, bottomTab: "tests" });
    try {
      const report = await api.runTests(eid, targets);
      set({ testReport: report });
      return report;
    } finally {
      set({ testsRunning: false });
    }
  },

  activeTask() {
    const data = get().data;
    if (!data) return null;
    return Object.values(data.tasks).find((t) => t.status === "active") ?? null;
  },

  async beginTask(kind) {
    const { eid } = get();
    if (!eid) return;
    await get().saveAll();
    await get().flush();
    const data = await api.beginTask(eid, kind);
    set({ data, rightTab: "brief" });
    await get().refreshTree();
    // Files may have changed on disk (e.g. acceptance tests added) — reload open models.
    for (const tab of get().tabs) {
      if (tab.external) continue;
      try {
        const { content } = await api.readFile(eid, tab.path);
        const model = getModel(tab.path);
        if (model && model.getValue() !== content) model.setValue(content);
      } catch {
        /* file may be gone */
      }
    }
  },

  reset() {
    set({ ...initial, changed: new Set(), dirty: new Set(), editedOnce: new Set(), queue: [] });
  },
}));
