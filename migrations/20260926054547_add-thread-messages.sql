-- The live incident thread: the contractor's messages, the characters' replies,
-- and the messages the thread posts on its own as an incident goes on.
-- Server-only, like every other Cold Start table.

CREATE TABLE IF NOT EXISTS public.thread_messages (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    engagement_id   text NOT NULL,
    task_id         text NOT NULL,
    ts              double precision NOT NULL,
    author          text NOT NULL,              -- 'You' or a character's name
    author_role     text,
    body            text NOT NULL,
    kind            text NOT NULL,              -- learner | reply | beat | resolution | hidden
    beat_id         text
);
CREATE INDEX IF NOT EXISTS thread_by_task ON public.thread_messages (task_id, id);

ALTER TABLE public.thread_messages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.thread_messages FROM anon, authenticated;
REVOKE ALL ON SEQUENCE public.thread_messages_id_seq FROM anon, authenticated;
