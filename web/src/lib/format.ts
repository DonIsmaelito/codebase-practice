export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(h ? 2 : 1, "0");
  const ss = String(sec).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function duration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  return rest ? `${h}h ${rest}m` : `${h}h`;
}

export function ago(epochSeconds: number): string {
  const diff = Date.now() / 1000 - epochSeconds;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  const days = Math.floor(diff / 86400);
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return new Date(epochSeconds * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Burning the midnight oil";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export function hashHue(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return h % 360;
}

export function initials(name: string): string {
  const words = name.replace(/[^A-Za-z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
  if (!words.length) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

export function languageFor(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  return (
    {
      py: "python",
      pyi: "python",
      md: "markdown",
      json: "json",
      jsonl: "json",
      toml: "ini",
      cfg: "ini",
      ini: "ini",
      yaml: "yaml",
      yml: "yaml",
      sql: "sql",
      html: "html",
      j2: "html",
      jinja: "html",
      sh: "shell",
      csv: "plaintext",
      txt: "plaintext",
    } as Record<string, string>
  )[ext] ?? "plaintext";
}

export function basename(path: string): string {
  return path.split("/").pop() ?? path;
}

export function dirname(path: string): string {
  const parts = path.split("/");
  parts.pop();
  return parts.join("/");
}

export const channelLabel: Record<string, string> = {
  slack: "Slack",
  email: "Email",
  jira: "Jira",
  pager: "Pager",
};

export const fidelityLabel: Record<string, string> = {
  failing_test: "CI is red",
  traceback: "Production traceback",
  repro_steps: "QA repro steps",
  user_report: "Customer complaint",
  logs: "On-call logs",
  vague: "Vague report",
  misleading: "Conflicting theories",
  metrics: "Metrics regression",
};

export const stateLabel: Record<string, string> = {
  fog: "Unexplored",
  glimpsed: "Glimpsed",
  practiced: "Practiced",
  solid: "Solid",
  mastered: "Mastered",
};
