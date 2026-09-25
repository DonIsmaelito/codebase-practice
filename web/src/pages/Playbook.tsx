import clsx from "clsx";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { Markdown, Spinner } from "../components/ui";
import { api } from "../lib/api";

export default function Playbook() {
  const { slug } = useParams();
  const [list, setList] = useState<{ slug: string; title: string; summary: string; order: number }[] | null>(null);
  const [article, setArticle] = useState<{ slug: string; title: string; summary: string; body: string } | null>(null);

  useEffect(() => {
    api.playbook().then(setList);
  }, []);
  const current = slug ?? list?.[0]?.slug;
  useEffect(() => {
    if (!current) return;
    setArticle(null);
    api.article(current).then(setArticle);
    window.scrollTo({ top: 0 });
  }, [current]);

  if (!list) return <div className="grid h-[60vh] place-items-center"><Spinner className="size-6" /></div>;
  const idx = list.findIndex((a) => a.slug === current);
  const next = list[idx + 1];

  return (
    <div className="mx-auto grid max-w-[1180px] gap-10 px-6 py-10 lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="lg:sticky lg:top-20 lg:h-fit">
        <h1 className="font-serif text-[36px] leading-none text-fg-0">Playbook</h1>
        <p className="mt-2 text-[13px] text-fg-2">How experienced engineers get their bearings, hunt bugs, and ship in code they didn't write.</p>
        <nav className="mt-6 space-y-0.5">
          {list.map((a, i) => (
            <Link
              key={a.slug}
              to={`/playbook/${a.slug}`}
              className={clsx("flex gap-3 rounded-lg px-3 py-2 text-[13px]", a.slug === current ? "bg-ink-3 text-fg-0" : "text-fg-2 hover:text-fg-0")}
            >
              <span className="w-4 shrink-0 font-mono text-[11px] text-fg-3 tabular-nums">{i + 1}</span>
              {a.title}
            </Link>
          ))}
        </nav>
      </aside>
      <article className="min-w-0">
        {!article ? (
          <Spinner />
        ) : (
          <>
            <div className="text-[12px] font-semibold tracking-[0.1em] text-teal uppercase">Playbook · {idx + 1} of {list.length}</div>
            <h2 className="mt-2 font-serif text-[44px] leading-[1.08] text-fg-0">{article.title}</h2>
            <p className="mt-3 text-[16px] text-fg-1 italic">{article.summary}</p>
            <Markdown large className="mt-8 max-w-[720px]">{article.body}</Markdown>
            {next && (
              <Link to={`/playbook/${next.slug}`} className="mt-12 block max-w-[720px] rounded-2xl border border-line bg-ink-1 p-5 transition hover:border-line-strong">
                <div className="text-[12px] text-fg-2">Next</div>
                <div className="mt-1 text-[16px] text-fg-0">{next.title}</div>
              </Link>
            )}
          </>
        )}
      </article>
    </div>
  );
}
