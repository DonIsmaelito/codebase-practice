-- Cold Start application state (progress, engagements, spend ledger).
--
-- These tables are read and written ONLY by the Cold Start server over its
-- direct Postgres connection. The browser never talks to them through the REST
-- API, so row level security is enabled with no policies and the default
-- anon/authenticated privileges are revoked: PostgREST access is denied twice.
--
-- JSON payloads are stored as text: the server owns (de)serialization and
-- nothing filters inside them.

CREATE TABLE IF NOT EXISTS public.cases (
    id          text PRIMARY KEY,
    created_at  double precision NOT NULL,
    status      text NOT NULL,                  -- queued | generating | ready | failed | taken | dismissed
    stage       text,                           -- pipeline heartbeat while generating
    spec        text NOT NULL,
    card        text,
    error       text,
    cost_usd    double precision NOT NULL DEFAULT 0,
    finished_at double precision
);

CREATE TABLE IF NOT EXISTS public.engagements (
    id          text PRIMARY KEY,
    case_id     text NOT NULL REFERENCES public.cases(id),
    started_at  double precision NOT NULL,
    ended_at    double precision,
    status      text NOT NULL,                  -- active | done | abandoned
    phase       text NOT NULL,
    plan        text NOT NULL,
    notes       text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS public.tasks (
    id              text PRIMARY KEY,
    engagement_id   text NOT NULL REFERENCES public.engagements(id),
    kind            text NOT NULL,              -- recon | incident | feature
    status          text NOT NULL,
    started_at      double precision,
    finished_at     double precision,
    active_seconds  double precision NOT NULL DEFAULT 0,
    hints_used      integer NOT NULL DEFAULT 0,
    attempts        integer NOT NULL DEFAULT 0,
    base_commit     text,
    result          text
);
CREATE INDEX IF NOT EXISTS tasks_by_engagement ON public.tasks (engagement_id);

CREATE TABLE IF NOT EXISTS public.events (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    engagement_id   text NOT NULL,
    task_id         text,
    ts              double precision NOT NULL,
    kind            text NOT NULL,
    data            text
);
CREATE INDEX IF NOT EXISTS events_by_task ON public.events (task_id, ts);

CREATE TABLE IF NOT EXISTS public.chat (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    engagement_id   text NOT NULL,
    task_id         text,
    ts              double precision NOT NULL,
    role            text NOT NULL,
    content         text NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_by_task ON public.chat (task_id, id);

CREATE TABLE IF NOT EXISTS public.mastery (
    concept_id  text PRIMARY KEY,
    data        text NOT NULL,
    updated_at  double precision NOT NULL
);

CREATE TABLE IF NOT EXISTS public.journal (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at      double precision NOT NULL,
    case_id         text,
    engagement_id   text,
    task_id         text,
    concept_ids     text NOT NULL DEFAULT '[]',
    title           text NOT NULL,
    lesson          text NOT NULL,
    snippet         text,
    recall_q        text,
    recall_a        text,
    recall_due      double precision,
    recall_interval double precision NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS journal_by_recall ON public.journal (recall_due);

CREATE TABLE IF NOT EXISTS public.practice_days (
    day      text PRIMARY KEY,                  -- YYYY-MM-DD, learner's local time
    seconds  double precision NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS public.llm_calls (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts                double precision NOT NULL,
    role              text,
    model             text,
    case_id           text,
    prompt_tokens     integer,
    completion_tokens integer,
    cached_tokens     integer,
    cost_usd          double precision,
    duration_s        double precision,
    ok                integer NOT NULL,
    error             text
);

CREATE TABLE IF NOT EXISTS public.kv (
    key    text PRIMARY KEY,
    value  text NOT NULL
);

CREATE TABLE IF NOT EXISTS public.drills (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at  double precision NOT NULL,
    concept_id  text NOT NULL,
    kind        text NOT NULL,
    payload     text NOT NULL,
    answered_at double precision,
    correct     integer,
    given       text
);
CREATE INDEX IF NOT EXISTS drills_unanswered ON public.drills (answered_at, id);

-- Server-only: deny the REST API entirely.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['cases', 'engagements', 'tasks', 'events', 'chat', 'mastery',
                           'journal', 'practice_days', 'llm_calls', 'kv', 'drills']
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
  END LOOP;
END $$;

REVOKE ALL ON SEQUENCE public.events_id_seq, public.chat_id_seq, public.journal_id_seq,
                       public.llm_calls_id_seq, public.drills_id_seq
    FROM anon, authenticated;
