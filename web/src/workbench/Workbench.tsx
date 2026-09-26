import clsx from "clsx";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, Compass, EyeOff, FileSearch, Files, GitCompareArrows, HelpCircle, ListTree, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { Group, Panel, Separator, usePanelRef } from "react-resizable-panels";
import { Link, useNavigate, useParams } from "react-router";
import { useShallow } from "zustand/react/shallow";
import { Avatar, Button, Kbd, Markdown, Monogram, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { authHeaders } from "../lib/auth";
import { useDesk } from "../lib/desk";
import { disposeAllModels, registerPythonIntel, setIntelContext } from "../lib/monaco";
import type { TaskKind } from "../lib/types";
import BottomPanel from "./BottomPanel";
import Debrief from "./Debrief";
import EditorArea from "./EditorArea";
import Explorer from "./Explorer";
import MissionPanel, { focusKind, Stepper } from "./MissionPanel";
import QuickOpen from "./QuickOpen";
import SearchPanel from "./SearchPanel";
import { ChangesPanel, OutlinePanel } from "./SidePanels";
import { useWB } from "./store";

export default function Workbench() {
  const { eid } = useParams();
  const navigate = useNavigate();
  const { data, side, sideOpen, bottomOpen, quickOpen, codeHidden } = useWB(
    useShallow((s) => ({ data: s.data, side: s.side, sideOpen: s.sideOpen, bottomOpen: s.bottomOpen, quickOpen: s.quickOpen, codeHidden: s.codeHidden })),
  );
  const { load, set, flush, openFile, log, reset } = useWB.getState();
  const [error, setError] = useState<string | null>(null);
  const [viewKind, setViewKind] = useState<TaskKind | null>(null);
  const [debrief, setDebrief] = useState<TaskKind | null>(null);
  const [help, setHelp] = useState(false);
  const sideRef = usePanelRef();
  const bottomRef = usePanelRef();

  // Load the engagement and wire editor intelligence to it.
  useEffect(() => {
    if (!eid) return;
    registerPythonIntel();
    setIntelContext({
      eid,
      open: (path, external, line, column) => void useWB.getState().openFile(path, external, line, column, line ? "flash" : undefined),
      log: (kind, d) => useWB.getState().log(kind, d),
    });
    load(eid).catch((e) => setError((e as Error).message));
    // beforeunload can't await a token refresh, so keep the latest headers around.
    let lastAuthHeaders: Record<string, string> = {};
    const refreshHeaders = () => void authHeaders().then((h) => (lastAuthHeaders = h));
    refreshHeaders();
    const flushId = window.setInterval(() => {
      void flush();
      refreshHeaders();
    }, 5000);
    const onUnload = () => {
      const { queue, eid: id } = useWB.getState();
      if (queue.length && id) {
        void fetch(`/api/engagements/${id}/events`, {
          method: "POST",
          keepalive: true,
          headers: { "Content-Type": "application/json", "X-Coldstart": "1", ...lastAuthHeaders },
          body: JSON.stringify({ events: queue }),
        });
      }
    };
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.clearInterval(flushId);
      window.removeEventListener("beforeunload", onUnload);
      void flush();
      setIntelContext(null);
      disposeAllModels();
      reset();
    };
  }, [eid, load, flush, reset]);

  // Open something useful on first load: README for recon, else the regression test.
  useEffect(() => {
    if (!data || useWB.getState().tabs.length) return;
    const readme = useWB.getState().tree.find((e) => e.path.toLowerCase() === "readme.md");
    if (readme) void openFile(readme.path);
  }, [data, openFile]);

  // Keep panel collapse state in sync with the store.
  useEffect(() => {
    const p = sideRef.current;
    if (!p) return;
    if (sideOpen && p.isCollapsed()) p.expand();
    if (!sideOpen && !p.isCollapsed()) p.collapse();
  }, [sideOpen, sideRef]);
  useEffect(() => {
    const p = bottomRef.current;
    if (!p) return;
    if (bottomOpen && p.isCollapsed()) p.expand();
    if (!bottomOpen && !p.isCollapsed()) p.collapse();
  }, [bottomOpen, bottomRef]);

  // Global shortcuts (capture phase so they work inside Monaco too).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) {
        if (e.key === "Escape" && useWB.getState().quickOpen) set({ quickOpen: false });
        return;
      }
      const k = e.key.toLowerCase();
      if (k === "p" && !e.shiftKey) {
        e.preventDefault();
        set({ quickOpen: true });
      } else if (k === "f" && e.shiftKey) {
        e.preventDefault();
        set({ side: "search", sideOpen: true });
      } else if (k === "e" && e.shiftKey) {
        e.preventDefault();
        set({ side: "files", sideOpen: true });
      } else if (k === "j") {
        e.preventDefault();
        set({ bottomOpen: !useWB.getState().bottomOpen });
      } else if (k === "b") {
        e.preventDefault();
        set({ sideOpen: !useWB.getState().sideOpen });
      } else if (k === "`") {
        e.preventDefault();
        set({ bottomOpen: true, bottomTab: "terminal" });
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [set]);

  if (error) {
    return (
      <div className="grid h-full place-items-center text-center">
        <div>
          <div className="text-red">{error}</div>
          <Link to="/" className="mt-3 inline-block text-blue">Back to the desk</Link>
        </div>
      </div>
    );
  }
  if (!data) return <div className="grid h-full place-items-center"><Spinner className="size-6" /></div>;

  const company = data.case.company;
  const briefing = !Object.values(data.tasks).some((t) => t.status !== "pending" && t.status !== "skipped");
  const finished = data.engagement.status !== "active";

  const endEngagement = async () => {
    if (!confirm("Wrap up this engagement? Unfinished tasks will be left as-is.")) return;
    await useWB.getState().saveAll();
    await flush();
    await api.endEngagement(data.engagement.id);
    void useDesk.getState().load();
    navigate(`/e/${data.engagement.id}/wrapup`);
  };

  const activity = [
    { id: "files" as const, icon: <Files className="size-[18px]" />, title: "Explorer (⌘⇧E)" },
    { id: "search" as const, icon: <FileSearch className="size-[18px]" />, title: "Search (⌘⇧F)" },
    { id: "changes" as const, icon: <GitCompareArrows className="size-[18px]" />, title: "Your changes" },
    { id: "outline" as const, icon: <ListTree className="size-[18px]" />, title: "Outline" },
  ];

  return (
    <div className="flex h-full flex-col bg-ink-0">
      <header className="flex h-11 shrink-0 items-center gap-3 border-b border-line px-3">
        <Link to="/" className="rounded-md p-1.5 text-fg-2 hover:bg-ink-3 hover:text-fg-0" title="Back to the desk">
          <ArrowLeft className="size-4" />
        </Link>
        <Monogram name={company.name} size={24} className="rounded-md" />
        <div className="min-w-0">
          <span className="font-serif text-[17px] text-fg-0">{company.name}</span>
          <span className="ml-2 font-mono text-[11.5px] text-fg-3">{data.case.repo.name}</span>
        </div>
        <div className="mx-auto">
          <Stepper data={data} viewKind={viewKind} onView={(k) => { setViewKind(k === focusKind(data) ? null : k); set({ rightTab: "brief" }); }} />
        </div>
        <button onClick={() => setHelp(true)} className="grid size-7 place-items-center rounded-md text-fg-2 hover:bg-ink-3 hover:text-fg-0" title="Shortcuts & tips">
          <HelpCircle className="size-4" />
        </button>
        {!finished ? (
          <Button size="sm" ghost icon={<LogOut className="size-3.5" />} onClick={() => void endEngagement()}>
            Wrap up
          </Button>
        ) : (
          <Link to={`/e/${data.engagement.id}/wrapup`} className="text-[12.5px] text-blue">Engagement summary →</Link>
        )}
      </header>

      <div className="flex min-h-0 flex-1">
        <nav className="flex w-11 shrink-0 flex-col items-center gap-1 border-r border-line bg-ink-0 pt-2">
          {activity.map((a) => (
            <button
              key={a.id}
              title={a.title}
              onClick={() => set(side === a.id && sideOpen ? { sideOpen: false } : { side: a.id, sideOpen: true })}
              className={clsx(
                "relative grid size-9 place-items-center rounded-lg transition-colors",
                side === a.id && sideOpen ? "text-fg-0" : "text-fg-3 hover:text-fg-1",
              )}
            >
              {side === a.id && sideOpen && <span className="absolute top-1.5 bottom-1.5 left-[-6px] w-[2px] rounded bg-blue" />}
              {a.icon}
            </button>
          ))}
        </nav>

        <Group orientation="horizontal" className="min-w-0 flex-1">
          <Panel id="side" panelRef={sideRef} defaultSize={250} minSize={170} maxSize={520} collapsible collapsedSize={0} groupResizeBehavior="preserve-pixel-size"
            onResize={(size) => { const open = size.inPixels > 0; if (open !== useWB.getState().sideOpen) set({ sideOpen: open }); }}>
            <div className="relative h-full overflow-hidden bg-ink-0">
              {side === "files" && <Explorer />}
              {side === "search" && <SearchPanel />}
              {side === "changes" && <ChangesPanel />}
              {side === "outline" && <OutlinePanel />}
              {codeHidden && <HiddenOverlay />}
            </div>
          </Panel>
          <Separator />
          <Panel id="center" minSize={320}>
            <Group orientation="vertical">
              <Panel id="editor" minSize={120}>
                <div className="relative h-full">
                  <EditorArea />
                  {codeHidden && <HiddenOverlay big />}
                </div>
              </Panel>
              <Separator />
              <Panel id="bottom" panelRef={bottomRef} defaultSize="32" minSize={90} collapsible collapsedSize={0}
                onResize={(size) => { const open = size.inPixels > 0; if (open !== useWB.getState().bottomOpen) set({ bottomOpen: open }); }}>
                <BottomPanel />
              </Panel>
            </Group>
          </Panel>
          <Separator />
          <Panel id="mission" defaultSize={430} minSize={340} maxSize={720} groupResizeBehavior="preserve-pixel-size">
            <MissionPanel data={data} viewKind={viewKind} onDebrief={(k) => setDebrief(k)} />
          </Panel>
        </Group>
      </div>

      {quickOpen && <QuickOpen />}
      <AnimatePresence>{briefing && !finished && <Intro key="intro" />}</AnimatePresence>
      {debrief && <Debrief data={data} kind={debrief} onClose={() => setDebrief(null)} />}
      {help && <HelpSheet onClose={() => setHelp(false)} />}
    </div>
  );

  function Intro() {
    const [starting, setStarting] = useState(false);
    const first: TaskKind = data!.engagement.plan.includes("recon") ? "recon" : "incident";
    const b = data!.case.recon.briefing;
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-40 grid place-items-center bg-ink-0/85 backdrop-blur-md">
        <motion.div initial={{ y: 14, opacity: 0 }} animate={{ y: 0, opacity: 1, transition: { delay: 0.1 } }} className="w-[560px] max-w-[92vw] rounded-3xl border border-line-strong bg-ink-1 p-8 shadow-2xl">
          <div className="text-[12px] font-semibold tracking-[0.12em] text-blue uppercase">Day one</div>
          <div className="mt-2 flex items-center gap-4">
            <Monogram name={company.name} size={52} />
            <div>
              <div className="font-serif text-[34px] leading-none text-fg-0">{company.name}</div>
              <div className="mt-1 text-[13px] text-fg-2">{company.tagline}</div>
            </div>
          </div>
          {first === "recon" && (
            <div className="mt-6 flex gap-2.5">
              <Avatar name={b.from} size={28} />
              <div className="min-w-0 flex-1 rounded-xl rounded-tl-sm border border-line bg-ink-2/70 px-3.5 py-3">
                <div className="text-[12.5px] font-semibold text-fg-0">{b.from}</div>
                <div className="mt-1 max-h-40 overflow-hidden [mask-image:linear-gradient(to_bottom,black_70%,transparent)]">
                  <Markdown className="text-[13px]">{b.body}</Markdown>
                </div>
              </div>
            </div>
          )}
          {data!.habit && (
            <div className="mt-5 rounded-xl border border-teal/20 bg-teal-dim/30 px-4 py-3">
              <div className="text-[11px] font-semibold tracking-[0.08em] text-teal uppercase">Your habit for this one · from {data!.habit.company}</div>
              <Markdown className="mt-1 text-[13.5px] [&_p]:text-fg-0">{data!.habit.text}</Markdown>
            </div>
          )}
          <p className="mt-5 text-[13.5px] leading-relaxed text-fg-1">
            {first === "recon"
              ? "Get your bearings before anything breaks. Nobody reads everything — read with a question."
              : "Straight into the fire. Read the report carefully; the details are clues."}
          </p>
          <div className="mt-6 flex items-center gap-3">
            <Button tone={first === "recon" ? "blue" : "amber"} size="lg" loading={starting} icon={<Compass className="size-4" />}
              onClick={async () => { setStarting(true); await useWB.getState().beginTask(first); log("clock_in", {}); }}>
              {first === "recon" ? "Start recon" : "Open the incident"}
            </Button>
            <span className="text-[12px] text-fg-3">The timer starts now.</span>
          </div>
        </motion.div>
      </motion.div>
    );
  }
}

function HiddenOverlay({ big }: { big?: boolean }) {
  return (
    <div className="absolute inset-0 z-20 grid place-items-center bg-ink-0/90 backdrop-blur-xl">
      {big && (
        <div className="text-center">
          <EyeOff className="mx-auto size-7 text-blue" />
          <div className="mt-3 text-[15px] text-fg-0">Code hidden while you answer</div>
          <div className="mt-1 text-[13px] text-fg-2">Answer from your mental model. Retrieval is what makes it stick.</div>
        </div>
      )}
    </div>
  );
}

const SHORTCUTS: [string[], string][] = [
  [["⌘", "P"], "Go to file — type `name:42` to jump to a line"],
  [["⌘", "⇧", "F"], "Search the whole codebase"],
  [["F12"], "Go to definition (also ⌘-click) — works into the stdlib and libraries"],
  [["⇧", "F12"], "Find every reference"],
  [["⌘", "⇧", "O"], "Jump to a function or class in this file"],
  [["⌘", "J"], "Toggle the terminal / tests panel"],
  [["⌘", "B"], "Toggle the sidebar"],
  [["⌘", "S"], "Save (files also autosave)"],
  [["⌘", "F"], "Find in file"],
];

const TIPS = [
  "Click any `file.py:42` in a traceback or test failure to jump straight there.",
  "Select code, then ask the mentor about it — it sees your selection, open file and your diff.",
  "`python -i -c 'from pkg.module import thing'` drops you into a REPL with the code loaded.",
  "`pytest -x -k name -vv` runs just the tests you care about and stops at the first failure.",
  "`breakpoint()` in the code + `pytest -s` gives you a live debugger (`n`, `s`, `p expr`, `c`).",
  "`git diff` shows everything you've changed; the Changes view shows it per task.",
];

function HelpSheet({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 backdrop-blur-sm" onMouseDown={onClose}>
      <div className="w-[640px] max-w-[92vw] rounded-2xl border border-line-strong bg-ink-1 p-6 shadow-2xl" onMouseDown={(e) => e.stopPropagation()}>
        <div className="font-serif text-[26px] text-fg-0">Moving fast in here</div>
        <div className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-[auto_1fr]">
          {SHORTCUTS.map(([keys, what]) => (
            <div key={what} className="contents">
              <div className="flex items-center gap-1">{keys.map((k) => <Kbd key={k}>{k}</Kbd>)}</div>
              <Markdown className="text-[13px]">{what}</Markdown>
            </div>
          ))}
        </div>
        <div className="mt-5 border-t border-line pt-4">
          <div className="text-[12px] font-semibold tracking-[0.08em] text-fg-2 uppercase">Tips</div>
          <ul className="mt-2 space-y-1.5">
            {TIPS.map((t) => (
              <li key={t} className="flex gap-2"><span className="text-teal">›</span><Markdown className="text-[13px]">{t}</Markdown></li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
