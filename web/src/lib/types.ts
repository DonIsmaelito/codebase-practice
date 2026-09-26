// Shapes of the JSON the Python server returns. Kept in one place so the
// whole UI agrees on what a case, task, or debrief looks like.

export type TaskKind = "recon" | "incident" | "feature";
export type TaskStatus = "pending" | "active" | "passed" | "failed" | "revealed" | "skipped";
export type Outcome = "clean" | "assisted" | "revealed" | "failed";
export type MasteryState = "fog" | "glimpsed" | "practiced" | "solid" | "mastered";

export interface Person {
  name: string;
  role: string;
  voice?: string;
}

export interface Company {
  name: string;
  tagline: string;
  industry: string;
  blurb: string;
  team: Person[];
}

export interface RepoStats {
  files: number;
  py_files: number;
  test_files: number;
  loc: number;
  test_loc: number;
}

export interface CaseCard {
  id: string;
  company: string;
  tagline: string;
  industry: string;
  blurb: string;
  subject: string;
  channel: string;
  from: string;
  shape: string;
  libraries: string[];
  stats: RepoStats;
  level: number;
  fidelity: string;
  minutes: { recon: number; incident: number; feature: number };
  domain: string;
  sector: string;
  arrived_at?: number;
}

export interface PipelineItem {
  id: string;
  status: "queued" | "generating";
  stage: { key: string; label: string; detail: string; progress: number | null; ts: number } | null;
  domain: string | null;
  created_at: number;
}

export interface Budget {
  ok: boolean;
  limit?: number | null;
  remaining?: number | null; // what can actually be spent: min(account balance, key limit left)
  key_remaining?: number | null;
  account_remaining?: number | null;
  usage?: number;
  error?: string;
}

export interface Settings {
  models: Record<string, string>;
  buffer_size: number;
  auto_generate: boolean;
  budget_floor_usd: number;
  daily_budget_usd: number;
  default_plan: TaskKind[];
  timer_mode: "stopwatch" | "countdown";
  mentor_name: string;
  sound: boolean;
  coach_nudges: boolean;
}

export interface Learner {
  level: number;
  created_at: number;
}

export interface RecallCard {
  id: number;
  title: string;
  recall_q: string;
  recall_a: string;
  case_id: string;
  concept_ids: string[];
}

export interface DeskState {
  inbox: CaseCard[];
  pipeline: PipelineItem[];
  last_failure: { id: string; error: string; finished_at: number } | null;
  manager: { running: string[]; paused_until: number | null; consecutive_failures: number; last_error: string | null };
  active: { id: string; company: string; phase: string; subject: string; started_at: number } | null;
  recall: RecallCard | null;
  calendar: { day: string; seconds: number }[];
  engagements_done: number;
  first_run: boolean;
  budget: Budget;
  settings: Settings;
  learner: Learner;
}

export interface Message {
  from: string;
  role?: string;
  time?: string;
  body: string;
}

export interface Report {
  channel: string;
  title: string;
  messages: Message[];
  ask: string;
}

export interface TourStop {
  path: string;
  anchor: string;
  line: number;
  title: string;
  note: string;
}

export interface MapInfo {
  summary: string;
  components: { name: string; paths: string[]; role: string }[];
  flows: { name: string; steps: string[] }[];
}

export interface ConceptCard {
  headline: string;
  explanation: string;
  example: string;
  spot_it: string[];
  elsewhere: string[];
}

export interface ExpertStep {
  step: string;
  why: string;
}

export interface IncidentSolution {
  title: string;
  root_cause: string;
  root_cause_file: string;
  root_cause_symbol: string;
  files_involved: string[];
  mechanism: string;
  fix: string;
  fix_diff: string;
  expert_path: ExpertStep[];
  concept_card: ConceptCard;
  repro: string;
  hidden_tests: string;
}

export interface FeatureSolution {
  reference_diff: string;
  expert_path: ExpertStep[];
  review_focus: string[];
  concept_card: ConceptCard;
  hidden_tests: string;
}

export interface Ticket {
  background: string;
  requirements: string[];
  acceptance: string[];
  interface: string;
  examples: string;
  out_of_scope: string[];
  notes: string;
}

export interface PublicCase {
  id: string;
  company: Company;
  repo: {
    name: string;
    package: string;
    shape: string;
    summary: string;
    entry_points: string[];
    libraries: string[];
    stats: RepoStats;
  };
  card: CaseCard;
  feature_ready: boolean;
  feature_author?: string | null;
  concepts: { incident: string | null; feature: string | null; flavor: string[] };
  recon: {
    mode: "guided" | "open" | "closed";
    par_minutes: number;
    briefing: { from: string; role?: string; body: string };
    tour: TourStop[];
    questions: { id: string; kind: string; prompt: string }[];
    map: MapInfo | null;
  };
  incident?: {
    report: Report;
    fidelity: string;
    par_minutes: number;
    regression_test: string | null;
    solution?: IncidentSolution;
  };
  feature?: {
    title: string;
    author: Person;
    ticket: Ticket;
    par_minutes: number;
    acceptance_path: string;
    solution?: FeatureSolution;
  };
}

export interface ReconResult {
  results: { id: string; verdict: "correct" | "partial" | "incorrect"; feedback: string; answer: string; given: string }[];
  overall: string;
  accuracy: number;
  seconds: number;
  map: MapInfo;
}

export interface IncidentReview {
  explanation_verdict: "correct" | "partial" | "incorrect" | "missing";
  explanation_feedback: string;
  fix_quality: string;
  fix_review: string;
  process_review: string;
  communication_review?: string;
  strengths: string[];
  next_time: string;
  lesson: string;
}

export interface FeatureReview {
  verdict: "ship" | "ship-with-nits" | "needs-work";
  summary: string;
  comments: { path: string; line: number; severity: "blocker" | "suggestion" | "nit" | "praise"; body: string }[];
  idioms: string[];
  complexity: string;
  process_review: string;
  strengths: string[];
  next_time: string;
  lesson: string;
}

export interface TaskResult {
  outcome?: Outcome;
  passed?: boolean;
  seconds?: number;
  par_seconds?: number;
  hints_used?: number;
  attempts?: number;
  mentor_messages?: number;
  time_to_root_file?: number | null;
  concept?: { id: string; state: MasteryState; before: MasteryState };
  review?: IncidentReview & FeatureReview;
  explanation?: string;
  learner_diff?: string;
  timeline?: string;
  solution?: IncidentSolution & FeatureSolution;
  previous_encounters?: { company: string; subject: string; lesson: string; when: number; case_id: string }[];
  speed?: { root_file_seconds: number | null; usual_root_file_seconds: number | null; par_ratio: number | null; usual_par_ratio: number | null };
  journal_id?: number;
  // recon
  results?: ReconResult["results"];
  overall?: string;
  accuracy?: number;
  map?: MapInfo;
}

export interface Task {
  id: string;
  kind: TaskKind;
  status: TaskStatus;
  started_at: number | null;
  finished_at: number | null;
  active_seconds: number;
  hints_used: number;
  attempts: number;
  result: TaskResult | null;
}

export interface EngagementPayload {
  engagement: {
    id: string;
    case_id: string;
    status: "active" | "done" | "abandoned";
    phase: "briefing" | TaskKind | "wrapup";
    plan: TaskKind[];
    started_at: number;
    ended_at: number | null;
    notes: string;
  };
  case: PublicCase;
  tasks: Record<TaskKind, Task>;
  hints: Partial<Record<TaskKind, string[]>>;
  hint_total: { incident: number; feature: number };
  settings: { mentor_name: string; timer_mode: string; sound: boolean; coach_nudges: boolean };
  habit: { text: string; company: string; case_id: string; ts: number } | null;
}

export interface TreeEntry {
  path: string;
  type: "file" | "dir";
  size?: number;
}

export interface TestCaseResult {
  nodeid: string;
  file: string;
  name: string;
  outcome: "passed" | "failed" | "error" | "skipped";
  duration_s: number;
  message: string;
  details: string;
}

export interface TestReport {
  passed: number;
  failed: number;
  errors: number;
  skipped: number;
  total: number;
  exit_code: number;
  timed_out: boolean;
  duration_s: number;
  output: string;
  cases: TestCaseResult[];
  ok: boolean;
}

export interface SubmitResult {
  passed: boolean;
  counts: { passed: number; failed: number; errors: number; total: number };
  failing: { nodeid: string; hidden: boolean; message: string; details: string }[];
  timed_out: boolean;
  output_tail: string;
}

export interface SearchResult {
  results: { path: string; matches: { line: number; column: number; length: number; text: string }[] }[];
  total: number;
  truncated: boolean;
  error?: string;
}

export interface Location {
  path: string;
  external: boolean;
  line: number;
  column: number;
  name: string;
  type: string;
}

export interface Change {
  path: string;
  status: "added" | "modified" | "deleted";
  original: string;
  current: string;
}

export interface Concept {
  id: string;
  name: string;
  region: string;
  tier: number;
  summary: string;
  prereqs: string[];
  bug_patterns: string[];
  feature_patterns: string[];
  beacons: string[];
  state: MasteryState;
  attempts: number;
  successes: number;
  due: number | null;
  last_seen: number | null;
  journal: { journal_id: number; title: string; lesson: string; when: number }[];
}

export interface Region {
  id: string;
  name: string;
  blurb: string;
}

export interface JournalEntry {
  id: number;
  created_at: number;
  case_id: string;
  engagement_id: string;
  task_id: string;
  concept_ids: string[];
  concepts: { id: string; name: string; region: string }[];
  title: string;
  lesson: string;
  snippet: string | null;
  recall_q: string | null;
  recall_a: string | null;
  company: string | null;
  subject: string | null;
}

export interface ProgressRow {
  id: string;
  when: number;
  company: string;
  domain: string;
  level: number;
  loc: number;
  files: number;
  recon_accuracy: number | null;
  recon_seconds: number | null;
  incident: { outcome: Outcome; seconds: number; par_seconds: number; time_to_root_file: number | null; hints_used: number } | null;
  feature: { outcome: Outcome; seconds: number; par_seconds: number; hints_used: number } | null;
}

export interface ChatMessage {
  role: "user" | "assistant" | "nudge"; // nudge = the mentor checking in unprompted
  content: string;
  ts?: number;
}

export interface ThreadMessage {
  id: number;
  ts: number;
  author: string;
  author_role: string | null;
  body: string;
  kind: "learner" | "reply" | "beat" | "resolution";
}

export interface Nudge {
  id: number;
  ts: number;
  content: string;
}

export interface LivePayload {
  thread: ThreadMessage[];
  typing: string | null;
  reply_error: string | null;
  cast: "ready" | "generating" | "failed" | "none" | null;
  nudges: Nudge[];
}

export type ReplayKind = "read" | "search" | "run" | "think" | "fix" | "verify";

export interface ReplayStep {
  kind: ReplayKind;
  say: string;
  at: number;
  you_at: number | null;
  path?: string;
  line?: number;
  end_line?: number | null;
  query?: string;
  hits?: { path: string; line: number; text: string }[];
  command?: string;
  output?: string;
  exit_code?: number;
  diff?: string;
}

export interface ReplayPayload {
  status: "ready" | "generating" | "failed" | "none";
  error?: string | null;
  steps?: ReplayStep[];
  takeaway?: string;
  files?: Record<string, string>;
  fixed?: Record<string, string>;
  expert_seconds?: number;
  your_seconds?: number;
}
