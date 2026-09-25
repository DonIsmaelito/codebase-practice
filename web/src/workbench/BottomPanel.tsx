import clsx from "clsx";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, FlaskConical, Play, RotateCw, SquareTerminal, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { Button, EmptyState, Spinner } from "../components/ui";
import type { TestCaseResult } from "../lib/types";
import { findRefs } from "./links";
import { useWB } from "./store";
import Terminal from "./Terminal";

export default function BottomPanel() {
  const { bottomTab, testsRunning, testReport } = useWB(
    useShallow((s) => ({ bottomTab: s.bottomTab, testsRunning: s.testsRunning, testReport: s.testReport })),
  );
  const set = useWB.getState().set;
  const tabs = [
    { id: "terminal" as const, label: "Terminal", icon: <SquareTerminal className="size-3.5" /> },
    {
      id: "tests" as const,
      label: "Tests",
      icon: <FlaskConical className="size-3.5" />,
      badge: testsRunning ? <Spinner className="size-3" /> : testReport ? (
        <span className={clsx("rounded px-1 font-mono text-[10px]", testReport.ok ? "bg-green-dim text-green" : "bg-red-dim text-red")}>
          {testReport.ok ? testReport.passed : testReport.failed + testReport.errors}
        </span>
      ) : null,
    },
  ];
  return (
    <div className="flex h-full flex-col bg-ink-1">
      <div className="flex h-8 shrink-0 items-center gap-1 border-b border-line px-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => set({ bottomTab: t.id })}
            className={clsx(
              "inline-flex items-center gap-1.5 rounded px-2 py-1 text-[12px]",
              bottomTab === t.id ? "bg-ink-3 text-fg-0" : "text-fg-2 hover:text-fg-1",
            )}
          >
            {t.icon}
            {t.label}
            {t.badge}
          </button>
        ))}
        <button className="ml-auto rounded p-1 text-fg-2 hover:bg-ink-3 hover:text-fg-0" onClick={() => set({ bottomOpen: false })} title="Hide panel (⌘J)">
          <ChevronDown className="size-3.5" />
        </button>
      </div>
      <div className="relative min-h-0 flex-1">
        <div className={clsx("absolute inset-0", bottomTab !== "terminal" && "invisible")}>
          <Terminal visible={bottomTab === "terminal"} />
        </div>
        {bottomTab === "tests" && (
          <div className="absolute inset-0">
            <TestsPanel />
          </div>
        )}
      </div>
    </div>
  );
}

function TestsPanel() {
  const { testReport: report, testsRunning: running, tree } = useWB(
    useShallow((s) => ({ testReport: s.testReport, testsRunning: s.testsRunning, tree: s.tree })),
  );
  const { runTests, openFile } = useWB.getState();
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const known = useMemo(() => new Set(tree.filter((e) => e.type === "file").map((e) => e.path)), [tree]);

  const failing = report?.cases.filter((c) => c.outcome === "failed" || c.outcome === "error") ?? [];
  const byFile = useMemo(() => {
    const m = new Map<string, TestCaseResult[]>();
    for (const c of report?.cases ?? []) m.set(c.file, [...(m.get(c.file) ?? []), c]);
    return m;
  }, [report]);

  const linkify = (text: string) => {
    const refs = findRefs(text, known);
    if (!refs.length) return text;
    const out: React.ReactNode[] = [];
    let last = 0;
    refs.forEach((r, i) => {
      out.push(text.slice(last, r.start));
      out.push(
        <button key={i} className="text-blue underline decoration-blue/40 underline-offset-2 hover:decoration-blue" onClick={() => void openFile(r.path, false, r.line, 1, "flash")}>
          {text.slice(r.start, r.end)}
        </button>,
      );
      last = r.end;
    });
    out.push(text.slice(last));
    return out;
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center gap-2 px-3 py-2">
        <Button size="sm" tone="green" icon={<Play className="size-3" />} loading={running} onClick={() => void runTests()}>
          Run all tests
        </Button>
        {failing.length > 0 && (
          <Button size="sm" icon={<RotateCw className="size-3" />} disabled={running} onClick={() => void runTests(failing.map((f) => f.nodeid))}>
            Rerun failing
          </Button>
        )}
        {report && (
          <span className="ml-2 text-[12px] text-fg-2">
            <span className="text-green">{report.passed} passed</span>
            {report.failed > 0 && <span className="text-red"> · {report.failed} failed</span>}
            {report.errors > 0 && <span className="text-red"> · {report.errors} errors</span>}
            {report.timed_out && <span className="text-amber"> · timed out</span>}
            <span className="text-fg-3"> · {report.duration_s.toFixed(1)}s</span>
          </span>
        )}
        <span className="ml-auto text-[11.5px] text-fg-3">The repo's own suite. The client's hidden checks run when you submit.</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3 font-mono text-[12px]">
        {!report && !running && <EmptyState title="No test run yet">Run the suite to see where things stand. Tip: `pytest -x -k name` in the terminal for a focused run.</EmptyState>}
        {report && report.cases.length === 0 && (
          <pre className="px-2 whitespace-pre-wrap text-red/90">{linkify(report.output || "No tests collected.")}</pre>
        )}
        {[...byFile.entries()].map(([file, cases]) => (
          <div key={file} className="mb-1">
            <div className="px-2 py-1 text-[11.5px] text-fg-2">{file}</div>
            {cases.map((c) => {
              const bad = c.outcome === "failed" || c.outcome === "error";
              const isOpen = openIds.has(c.nodeid) || (bad && failing.length <= 2 && !openIds.has("!" + c.nodeid));
              return (
                <div key={c.nodeid}>
                  <button
                    className="flex w-full items-center gap-1.5 rounded px-2 py-[3px] text-left hover:bg-ink-3"
                    onClick={() => {
                      const next = new Set(openIds);
                      if (isOpen) {
                        next.delete(c.nodeid);
                        next.add("!" + c.nodeid);
                      } else {
                        next.add(c.nodeid);
                        next.delete("!" + c.nodeid);
                      }
                      setOpenIds(next);
                    }}
                  >
                    {bad ? (isOpen ? <ChevronDown className="size-3 text-fg-3" /> : <ChevronRight className="size-3 text-fg-3" />) : <span className="w-3" />}
                    {c.outcome === "passed" ? (
                      <CheckCircle2 className="size-3.5 text-green" />
                    ) : c.outcome === "skipped" ? (
                      <AlertTriangle className="size-3.5 text-amber" />
                    ) : (
                      <XCircle className="size-3.5 text-red" />
                    )}
                    <span className={clsx(bad ? "text-fg-0" : "text-fg-1")}>{c.name}</span>
                    <span className="ml-auto text-[10.5px] text-fg-3">{(c.duration_s * 1000).toFixed(0)}ms</span>
                  </button>
                  {bad && isOpen && (
                    <pre className="mx-2 my-1 overflow-x-auto rounded-lg border border-red/15 bg-red-dim/30 p-2.5 text-[11.5px] leading-relaxed whitespace-pre-wrap text-fg-1">
                      {c.message && <div className="mb-1 text-red">{c.message}</div>}
                      {linkify(c.details)}
                    </pre>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
