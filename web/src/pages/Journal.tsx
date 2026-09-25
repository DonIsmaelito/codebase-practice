import clsx from "clsx";
import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { REGION_COLORS } from "../components/HexMap";
import { Card, Chip, EmptyState, Markdown, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { ago } from "../lib/format";
import type { JournalEntry } from "../lib/types";

export default function Journal() {
  const [entries, setEntries] = useState<JournalEntry[] | null>(null);
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState<string | null>(null);

  useEffect(() => {
    api.journal().then((r) => setEntries(r.entries));
  }, []);

  const regions = useMemo(() => [...new Set((entries ?? []).flatMap((e) => e.concepts.map((c) => c.region)))], [entries]);
  const shown = (entries ?? []).filter((e) => {
    if (region && !e.concepts.some((c) => c.region === region)) return false;
    if (!query) return true;
    const hay = `${e.title} ${e.lesson} ${e.company} ${e.concepts.map((c) => c.name).join(" ")}`.toLowerCase();
    return hay.includes(query.toLowerCase());
  });

  if (!entries) return <div className="grid h-[60vh] place-items-center"><Spinner className="size-6" /></div>;

  return (
    <div className="mx-auto max-w-[1080px] px-6 py-10">
      <h1 className="font-serif text-[42px] leading-none text-fg-0">Journal</h1>
      <p className="mt-2 text-[14.5px] text-fg-1">Every lesson from every client, in your own words. It's slowly becoming your personal Python handbook.</p>

      <div className="mt-8 flex flex-wrap items-center gap-2">
        <div className="flex w-72 items-center gap-2 rounded-lg border border-line-strong bg-ink-1 px-3 py-1.5 focus-within:border-blue">
          <Search className="size-3.5 text-fg-3" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search lessons" className="min-w-0 flex-1 bg-transparent text-[13px] text-fg-0 outline-none placeholder:text-fg-3" />
        </div>
        {regions.map((r) => (
          <button
            key={r}
            onClick={() => setRegion(region === r ? null : r)}
            className={clsx("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px]", region === r ? "border-line-strong bg-ink-3 text-fg-0" : "border-line text-fg-2 hover:text-fg-1")}
          >
            <span className="size-1.5 rounded-full" style={{ background: REGION_COLORS[r] }} />
            {r}
          </button>
        ))}
      </div>

      {entries.length === 0 ? (
        <Card className="mt-6">
          <EmptyState title="Your journal is empty">After each debrief, the lesson you take away lands here — and comes back later as quick recall, right when you're about to forget it.</EmptyState>
        </Card>
      ) : (
        <div className="mt-6 columns-1 gap-4 md:columns-2">
          {shown.map((e) => (
            <JournalCard key={e.id} entry={e} />
          ))}
        </div>
      )}
    </div>
  );
}

function JournalCard({ entry }: { entry: JournalEntry }) {
  const [lesson, setLesson] = useState(entry.lesson);
  const [showRecall, setShowRecall] = useState(false);
  return (
    <Card className="mb-4 break-inside-avoid p-5">
      <div className="flex flex-wrap items-center gap-1.5">
        {entry.concepts.map((c) => (
          <Chip key={c.id}>
            <span className="size-1.5 rounded-full" style={{ background: REGION_COLORS[c.region] }} />
            {c.name}
          </Chip>
        ))}
        <span className="ml-auto text-[11.5px] text-fg-3">{ago(entry.created_at)}</span>
      </div>
      <div className="mt-3 font-serif text-[22px] leading-snug text-fg-0">{entry.title}</div>
      {entry.company && <div className="mt-1 text-[12px] text-fg-2">{entry.company} · “{entry.subject}”</div>}
      <textarea
        value={lesson}
        onChange={(e) => setLesson(e.target.value)}
        onBlur={() => lesson !== entry.lesson && void api.updateJournal(entry.id, lesson)}
        rows={Math.max(2, Math.ceil(lesson.length / 60))}
        className="mt-3 w-full resize-none rounded-lg border border-transparent bg-transparent p-0 text-[14px] leading-relaxed text-fg-1 outline-none hover:border-line focus:border-line-strong focus:bg-ink-0 focus:p-2"
      />
      {entry.snippet && <Markdown className="mt-2">{entry.snippet.includes("```") ? entry.snippet : "```python\n" + entry.snippet + "\n```"}</Markdown>}
      {entry.recall_q && (
        <div className="mt-3 rounded-lg border border-teal/15 bg-teal-dim/20 px-3 py-2 text-[12.5px]">
          <div className="text-teal">{entry.recall_q}</div>
          {showRecall ? (
            <Markdown className="mt-1 text-[12.5px]">{entry.recall_a ?? ""}</Markdown>
          ) : (
            <button onClick={() => setShowRecall(true)} className="mt-1 text-[12px] text-fg-2 hover:text-fg-0">
              Show answer
            </button>
          )}
        </div>
      )}
    </Card>
  );
}
