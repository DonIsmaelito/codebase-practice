import { create } from "zustand";
import { api } from "../lib/api";
import { createModel, getModel, type monaco } from "../lib/monaco";
import type { EngagementPayload, LivePayload, Nudge, Task, TaskKind, TestReport, ThreadMessage, TreeEntry } from "../lib/types";

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

/** The live side of a task: the incident thread and the coach's check-ins. */
export interface LiveState {
  taskId: string | null;
  cursor: number; // highest thread id seen through polling (posts don't advance it)
  thread: ThreadMessage[];
  typing: string | null;
  replyError: string | null;
  nudges: Nudge[];
  cast: LivePayload["cast"];
}

const emptyLive = (taskId: string | null = null): LiveState => ({
  taskId, cursor: 0, thread: [], typing: null, replyError: null, nudges: [], cast: null,
});

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
  featurePreparing: boolean; // the optional ticket is being written on demand
  editedOnce: Set<string>;
  queue: { kind: string; data?: unknown; ts: number }[];
  live: LiveState;
  unread: { brief: number; mentor: number };
  nudgeToast: Nudge | null;
  replayTask: string | null; // the expert replay is open for this task

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
  takeFeature: () => Promise<void>;
  pollLive: (taskId: string, coachOn: boolean) => Promise<void>;
  postThread: (body: string) => Promise<void>;
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
  featurePreparing: false,
  editedOnce: new Set<string>(),
  queue: [] as { kind: string; data?: unknown; ts: number }[],
  live: emptyLive(),
  unread: { brief: 0, mentor: 0 },
  nudgeToast: null as Nudge | null,
  replayTask: null as string | null,
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

  async takeFeature() {
    const { eid } = get();
    if (!eid) return;
    const r = await api.prepareFeature(eid);
    if (r.status === "ready") {
      set({ featurePreparing: false });
      await get().beginTask("feature");
    } else {
      set({ featurePreparing: true, rightTab: "brief" });
    }
  },

  async pollLive(taskId, coachOn) {
    const before = get().live;
    const same = before.taskId === taskId;
    let r: LivePayload;
    try {
      r = await api.live(taskId, same ? before.cursor : 0, same ? (before.nudges.at(-1)?.id ?? 0) : 0, coachOn);
    } catch {
      return;
    }
    const cur = get().live.taskId === taskId ? get().live : emptyLive(taskId);
    const known = new Set(cur.thread.map((m) => m.id));
    const fresh = r.thread.filter((m) => !known.has(m.id));
    const knownNudges = new Set(cur.nudges.map((n) => n.id));
    const freshNudges = r.nudges.filter((n) => !knownNudges.has(n.id));
    const { rightTab, unread, nudgeToast } = get();
    // Only what arrives while you're here counts as new; the first poll is history.
    const incoming = same ? fresh.filter((m) => m.kind !== "learner").length : 0;
    set({
      live: {
        taskId,
        cursor: Math.max(cur.cursor, ...r.thread.map((m) => m.id)),
        thread: [...cur.thread, ...fresh].sort((a, b) => a.id - b.id),
        typing: r.typing,
        replyError: r.reply_error,
        nudges: [...cur.nudges, ...freshNudges],
        cast: r.cast,
      },
      unread: {
        brief: rightTab === "brief" ? 0 : unread.brief + incoming,
        mentor: rightTab === "mentor" ? 0 : unread.mentor + (same ? freshNudges.length : 0),
      },
      nudgeToast: same && freshNudges.length && rightTab !== "mentor" ? freshNudges[freshNudges.length - 1] : nudgeToast,
    });
  },

  async postThread(body) {
    const taskId = get().live.taskId;
    if (!taskId) return;
    const { message } = await api.postThread(taskId, body);
    const cur = get().live;
    if (cur.taskId !== taskId || cur.thread.some((m) => m.id === message.id)) return;
    // Show it now, and "typing…" until the poller hears back (the cursor stays put so nothing is skipped).
    set({ live: { ...cur, thread: [...cur.thread, message].sort((a, b) => a.id - b.id), typing: cur.typing ?? "", replyError: null } });
  },

  reset() {
    set({ ...initial, changed: new Set(), dirty: new Set(), editedOnce: new Set(), queue: [], live: emptyLive(), unread: { brief: 0, mentor: 0 } });
  },
}));
