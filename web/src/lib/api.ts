import type {
  Change,
  ChatMessage,
  Concept,
  DeskState,
  EngagementPayload,
  JournalEntry,
  Location,
  ProgressRow,
  ReconResult,
  Region,
  SearchResult,
  Settings,
  SubmitResult,
  TaskKind,
  TaskResult,
  TestReport,
  TreeEntry,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      // Required on every mutating request: other sites can't send custom
      // headers to localhost without a CORS preflight, which we never allow.
      "X-Coldstart": "1",
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const get = <T,>(url: string) => request<T>("GET", url);
const post = <T,>(url: string, body: unknown = {}) => request<T>("POST", url, body);
const put = <T,>(url: string, body: unknown) => request<T>("PUT", url, body);
const q = (params: Record<string, string | number | boolean | undefined>) =>
  new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)]),
  ).toString();

export const api = {
  state: () => get<DeskState>("/api/state"),
  generate: (focus?: string) => post<{ case_id: string }>("/api/cases/generate", { focus }),
  dismiss: (caseId: string) => post(`/api/cases/${caseId}/dismiss`),
  caseLog: (caseId: string) => get<{ log: string }>(`/api/cases/${caseId}/log`),

  startEngagement: (caseId: string, plan: TaskKind[]) =>
    post<EngagementPayload>("/api/engagements", { case_id: caseId, plan }),
  engagement: (eid: string) => get<EngagementPayload>(`/api/engagements/${eid}`),
  beginTask: (eid: string, kind: TaskKind) => post<EngagementPayload>(`/api/engagements/${eid}/tasks/${kind}/begin`),
  endEngagement: (eid: string, abandon = false) => post<EngagementPayload>(`/api/engagements/${eid}/end`, { abandon }),
  saveNotes: (eid: string, notes: string) => put(`/api/engagements/${eid}/notes`, { notes }),
  events: (eid: string, taskId: string | null, events: { kind: string; data?: unknown; ts?: number }[]) =>
    post(`/api/engagements/${eid}/events`, { task_id: taskId, events }),
  wrapup: (eid: string) => get<WrapupPayload>(`/api/engagements/${eid}/wrapup`),

  tick: (taskId: string, seconds: number) => post<{ active_seconds: number }>(`/api/tasks/${taskId}/tick`, { seconds }),
  hint: (taskId: string) => post<{ level: number; total: number; hints: string[] }>(`/api/tasks/${taskId}/hint`),
  recon: (taskId: string, answers: Record<string, string>) => post<ReconResult>(`/api/tasks/${taskId}/recon`, { answers }),
  submit: (taskId: string) => post<SubmitResult>(`/api/tasks/${taskId}/submit`),
  reveal: (taskId: string) => post(`/api/tasks/${taskId}/reveal`),
  debrief: (taskId: string, explanation: string) => post<TaskResult>(`/api/tasks/${taskId}/debrief`, { explanation }),
  chatHistory: (taskId: string) => get<{ messages: ChatMessage[] }>(`/api/tasks/${taskId}/chat`),

  tree: (eid: string) => get<{ entries: TreeEntry[]; changed: string[] }>(`/api/ws/${eid}/tree`),
  readFile: (eid: string, path: string) => get<{ path: string; content: string }>(`/api/ws/${eid}/file?${q({ path })}`),
  writeFile: (eid: string, path: string, content: string) => put(`/api/ws/${eid}/file`, { path, content }),
  fs: (eid: string, op: "create" | "delete" | "rename", path: string, extra: { to?: string; kind?: "file" | "dir" } = {}) =>
    post(`/api/ws/${eid}/fs`, { op, path, ...extra }),
  search: (eid: string, params: { q: string; regex?: boolean; case?: boolean; word?: boolean; include?: string }) =>
    get<SearchResult>(`/api/ws/${eid}/search?${q(params)}`),
  intel: <T,>(eid: string, op: "definition" | "references" | "hover", path: string, line: number, column: number, content?: string) =>
    post<T>(`/api/ws/${eid}/intel/${op}`, { path, line, column, content }),
  definition: (eid: string, path: string, line: number, column: number, content?: string) =>
    api.intel<Location[]>(eid, "definition", path, line, column, content),
  references: (eid: string, path: string, line: number, column: number, content?: string) =>
    api.intel<Location[]>(eid, "references", path, line, column, content),
  hover: (eid: string, path: string, line: number, column: number, content?: string) =>
    api.intel<{ name: string; type: string; module: string; signatures: string[]; doc: string } | null>(eid, "hover", path, line, column, content),
  symbols: (eid: string, path: string) =>
    get<{ name: string; type: string; line: number; column: number; parent: string | null }[]>(`/api/ws/${eid}/symbols?${q({ path })}`),
  external: (path: string) => get<{ path: string; content: string }>(`/api/external?${q({ path })}`),
  changes: (eid: string, taskId?: string) => get<{ task_id: string | null; changes: Change[] }>(`/api/ws/${eid}/changes?${q({ task_id: taskId })}`),
  revert: (eid: string, path?: string) => post(`/api/ws/${eid}/revert`, { path }),
  runTests: (eid: string, targets?: string[]) => post<TestReport>(`/api/ws/${eid}/tests`, { targets }),

  atlas: () => get<{ regions: Region[]; concepts: Concept[] }>("/api/atlas"),
  journal: () => get<{ entries: JournalEntry[] }>("/api/journal"),
  updateJournal: (id: number, lesson: string) => put(`/api/journal/${id}`, { lesson }),
  recall: (id: number, remembered: boolean) => post<{ next_in_days: number }>(`/api/recall/${id}`, { remembered }),
  progress: () => get<{ engagements: ProgressRow[]; calendar: { day: string; seconds: number }[] }>("/api/progress"),
  playbook: () => get<{ slug: string; title: string; summary: string; order: number }[]>("/api/playbook"),
  article: (slug: string) => get<{ slug: string; title: string; summary: string; body: string }>(`/api/playbook/${slug}`),
  settings: () => get<SettingsPayload>("/api/settings"),
  saveSettings: (patch: Partial<Settings> & { level?: number }) => put<{ settings: Settings }>("/api/settings", patch),
  models: () => get<{ id: string; name: string; prompt: number; completion: number; context: number }[]>("/api/models"),
};

export interface WrapupPayload {
  company: { name: string; team: { name: string; role: string }[]; tagline: string };
  tasks: Record<TaskKind, { status: string; result: TaskResult | null; active_seconds: number }>;
  concepts: (Omit<Concept, "state" | "attempts" | "successes" | "due" | "last_seen" | "journal"> & { mastery: string })[];
  next: { id: string; card: string } | null;
}

export interface SettingsPayload {
  settings: Settings;
  presets: Record<string, Record<string, string>>;
  learner: { level: number };
  spend: {
    total_usd: number;
    by_role: { role: string; model: string; calls: number; cost: number; prompt_tokens: number; completion_tokens: number; cached_tokens: number }[];
  };
  budget: { ok: boolean; limit?: number; remaining?: number; usage?: number };
}

/** Stream mentor replies over server-sent events. */
export async function streamChat(
  taskId: string,
  message: string,
  context: Record<string, unknown>,
  onDelta: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/tasks/${taskId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Coldstart": "1" },
    body: JSON.stringify({ message, context }),
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, "chat failed");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const data = JSON.parse(line.slice(5));
      if (data.error) throw new ApiError(502, data.error);
      if (data.t) onDelta(data.t);
    }
  }
}
