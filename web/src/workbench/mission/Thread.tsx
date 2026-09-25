import { AnimatePresence, motion } from "motion/react";
import { FileText, Hash, Mail, Radio } from "lucide-react";
import { useEffect, useState } from "react";
import { Avatar, Markdown } from "../../components/ui";
import { channelLabel } from "../../lib/format";
import type { Report } from "../../lib/types";

const icons: Record<string, typeof Hash> = { slack: Hash, email: Mail, jira: FileText, pager: Radio };

/** A report thread. On first view the messages arrive one by one, like the real thing. */
export default function Thread({ report, animate, onAllShown }: { report: Report; animate: boolean; onAllShown?: () => void }) {
  const [shown, setShown] = useState(animate ? 0 : report.messages.length);
  const Icon = icons[report.channel] ?? Hash;

  useEffect(() => {
    if (shown >= report.messages.length) {
      onAllShown?.();
      return;
    }
    const delay = shown === 0 ? 500 : Math.min(2200, 700 + report.messages[shown - 1].body.length * 4);
    const id = window.setTimeout(() => setShown((s) => s + 1), delay);
    return () => window.clearTimeout(id);
  }, [shown, report.messages, onAllShown]);

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-ink-2/60">
      <div className="flex items-center gap-2 border-b border-line px-3.5 py-2.5">
        <Icon className="size-3.5 text-amber" />
        <span className="truncate text-[13px] font-medium text-fg-0">{report.title}</span>
        <span className="ml-auto text-[11px] text-fg-3">{channelLabel[report.channel] ?? report.channel}</span>
      </div>
      <div className="space-y-4 px-3.5 py-3.5">
        <AnimatePresence initial={false}>
          {report.messages.slice(0, shown).map((m, i) => (
            <motion.div key={i} initial={animate ? { opacity: 0, y: 6 } : false} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }} className="flex gap-2.5">
              <Avatar name={m.from} size={26} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-[13px] font-semibold text-fg-0">{m.from}</span>
                  {m.role && <span className="truncate text-[11.5px] text-fg-2">{m.role}</span>}
                  {m.time && <span className="ml-auto shrink-0 text-[11px] text-fg-3">{m.time}</span>}
                </div>
                <Markdown className="mt-0.5 text-[13px]">{m.body}</Markdown>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {shown < report.messages.length && (
          <div className="flex items-center gap-2 pl-9 text-[11.5px] text-fg-3">
            <span className="flex gap-0.5">
              {[0, 1, 2].map((i) => (
                <span key={i} className="size-1 animate-breathe rounded-full bg-fg-3" style={{ animationDelay: `${i * 0.2}s` }} />
              ))}
            </span>
            {report.messages[shown]?.from} is typing…
          </div>
        )}
      </div>
      {shown >= report.messages.length && report.ask && (
        <div className="border-t border-line bg-amber-dim/40 px-3.5 py-2 text-[12.5px] text-amber">
          <span className="font-semibold">The ask:</span> {report.ask}
        </div>
      )}
    </div>
  );
}
