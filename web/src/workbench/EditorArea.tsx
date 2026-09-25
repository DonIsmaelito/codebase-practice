import clsx from "clsx";
import { ChevronRight, GitCompareArrows, Lock, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { EmptyState, Kbd } from "../components/ui";
import { api } from "../lib/api";
import { getModel, monaco, THEME } from "../lib/monaco";
import { fileIcon } from "./Explorer";
import { useShallow } from "zustand/react/shallow";
import { useWB } from "./store";

const EDITOR_OPTIONS: monaco.editor.IStandaloneEditorConstructionOptions = {
  theme: THEME,
  fontFamily: '"JetBrains Mono Variable", ui-monospace, Menlo, monospace',
  fontSize: 13.5,
  lineHeight: 21,
  fontLigatures: false,
  automaticLayout: true,
  minimap: { enabled: true, scale: 1, renderCharacters: false, maxColumn: 90 },
  scrollBeyondLastLine: false,
  smoothScrolling: true,
  cursorSmoothCaretAnimation: "on",
  cursorBlinking: "smooth",
  renderLineHighlight: "all",
  bracketPairColorization: { enabled: true },
  guides: { indentation: true, bracketPairs: false },
  stickyScroll: { enabled: true, maxLineCount: 3 },
  padding: { top: 10, bottom: 10 },
  tabSize: 4,
  insertSpaces: true,
  definitionLinkOpensInPeek: false,
  gotoLocation: { multipleDefinitions: "goto", multipleReferences: "peek" },
  fixedOverflowWidgets: true,
  scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10, useShadows: false },
  overviewRulerBorder: false,
  hover: { delay: 350 },
};

export default function EditorArea() {
  const { tabs, active, dirty, diffView, reveal, eid } = useWB(
    useShallow((s) => ({ tabs: s.tabs, active: s.active, dirty: s.dirty, diffView: s.diffView, reveal: s.reveal, eid: s.eid })),
  );
  const { closeTab, openFile, set, markDirty, save, setEditor } = useWB.getState();
  const hostRef = useRef<HTMLDivElement>(null);
  const diffHostRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const viewStates = useRef(new Map<string, monaco.editor.ICodeEditorViewState | null>());
  const currentKey = useRef<string | null>(null);
  const decorations = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);

  // Create the single code editor once; tabs swap models into it (like VS Code).
  useEffect(() => {
    if (!hostRef.current) return;
    const editor = monaco.editor.create(hostRef.current, { ...EDITOR_OPTIONS, model: null });
    editorRef.current = editor;
    decorations.current = editor.createDecorationsCollection();
    setEditor(editor);
    const sub = editor.onDidChangeModelContent(() => {
      const tab = useWB.getState().active;
      if (tab && !tab.external) markDirty(tab.path);
    });
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      const tab = useWB.getState().active;
      if (tab && !tab.external) void save(tab.path);
    });
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyP, () => set({ quickOpen: true }));
    return () => {
      sub.dispose();
      editor.dispose();
      setEditor(null);
      editorRef.current = null;
    };
  }, [markDirty, save, set, setEditor]);

  // Swap models when the active tab changes, keeping per-tab scroll/cursor.
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    if (currentKey.current) viewStates.current.set(currentKey.current, editor.saveViewState());
    if (!active) {
      editor.setModel(null);
      currentKey.current = null;
      return;
    }
    const key = `${active.external ? "ext" : "ws"}:${active.path}`;
    const model = getModel(active.path, active.external);
    if (!model) return;
    if (editor.getModel() !== model) {
      editor.setModel(model);
      const vs = viewStates.current.get(key);
      if (vs) editor.restoreViewState(vs);
    }
    editor.updateOptions({ readOnly: active.external, domReadOnly: active.external });
    currentKey.current = key;
    const r = useWB.getState().consumeReveal();
    if (r && r.path === active.path && r.external === active.external) {
      editor.revealLineInCenter(r.line, monaco.editor.ScrollType.Smooth);
      editor.setPosition({ lineNumber: r.line, column: r.column ?? 1 });
      if (r.highlight) {
        const end = r.endLine ?? r.line;
        decorations.current?.set([
          {
            range: new monaco.Range(r.line, 1, end, 1),
            options: {
              isWholeLine: true,
              className: r.highlight === "tour" ? "cs-tour-line" : "cs-flash-line",
              linesDecorationsClassName: r.highlight === "tour" ? "cs-tour-glyph" : undefined,
            },
          },
        ]);
        if (r.highlight === "flash") window.setTimeout(() => decorations.current?.clear(), 1600);
      } else decorations.current?.clear();
    } else {
      decorations.current?.clear();
    }
    editor.focus();
  }, [active, reveal]);

  // Diff view: original (task start) vs current, for the selected file.
  useEffect(() => {
    if (!diffView || !diffHostRef.current || !eid) return;
    const diff = monaco.editor.createDiffEditor(diffHostRef.current, {
      ...EDITOR_OPTIONS,
      renderSideBySide: true,
      readOnly: false,
      originalEditable: false,
      minimap: { enabled: false },
      renderOverviewRuler: false,
    });
    let original: monaco.editor.ITextModel | null = null;
    let alive = true;
    api.changes(eid).then(({ changes }) => {
      if (!alive) return;
      const change = changes.find((c) => c.path === diffView);
      const modified = getModel(diffView);
      if (!modified) return;
      original = monaco.editor.createModel(change?.original ?? modified.getValue(), modified.getLanguageId());
      diff.setModel({ original, modified });
    });
    return () => {
      alive = false;
      diff.setModel(null);
      diff.dispose();
      original?.dispose();
    };
  }, [diffView, eid]);

  const crumbs = active ? (active.external ? active.path.split("/").slice(-3) : active.path.split("/")) : [];

  return (
    <div className="flex h-full min-h-0 flex-col bg-ink-1">
      <div className="flex h-9 shrink-0 items-stretch overflow-x-auto border-b border-line bg-ink-0">
        {tabs.map((t) => {
          const isActive = active?.path === t.path && active.external === t.external;
          const name = t.path.split("/").pop() ?? t.path;
          return (
            <div
              key={`${t.external}:${t.path}`}
              onClick={() => void openFile(t.path, t.external)}
              onMouseDown={(e) => {
                if (e.button === 1) {
                  e.preventDefault();
                  closeTab(t);
                }
              }}
              className={clsx(
                "group flex max-w-[220px] shrink-0 cursor-pointer items-center gap-1.5 border-r border-line px-3 text-[12.5px]",
                isActive ? "bg-ink-1 text-fg-0 shadow-[inset_0_2px_0_var(--color-blue)]" : "text-fg-2 hover:text-fg-1",
              )}
              title={t.path}
            >
              {t.external ? <Lock className="size-3 text-fg-3" /> : fileIcon(name)}
              <span className={clsx("truncate", t.external && "italic")}>{name}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  closeTab(t);
                }}
                className="ml-1 grid size-4 place-items-center rounded hover:bg-ink-4"
              >
                {!t.external && dirty.has(t.path) ? (
                  <span className="size-2 rounded-full bg-fg-1 group-hover:hidden" />
                ) : null}
                <X className={clsx("size-3", !t.external && dirty.has(t.path) ? "hidden group-hover:block" : "opacity-0 group-hover:opacity-100")} />
              </button>
            </div>
          );
        })}
      </div>
      {active && (
        <div className="flex h-7 shrink-0 items-center gap-1 border-b border-line/60 px-3 text-[11.5px] text-fg-2">
          {active.external && <span className="mr-1 rounded bg-ink-3 px-1.5 text-[10.5px] text-fg-2">library source · read-only</span>}
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <ChevronRight className="size-3 text-fg-3" />}
              <span className={i === crumbs.length - 1 ? "text-fg-1" : ""}>{c}</span>
            </span>
          ))}
          {diffView && (
            <button onClick={() => set({ diffView: null })} className="ml-auto inline-flex items-center gap-1 rounded bg-violet-dim px-1.5 text-violet">
              <GitCompareArrows className="size-3" /> diff vs task start · close
            </button>
          )}
        </div>
      )}
      <div className="relative min-h-0 flex-1">
        <div ref={hostRef} className={clsx("absolute inset-0", (diffView || !active) && "invisible")} />
        {diffView && <div ref={diffHostRef} className="absolute inset-0" />}
        {!active && (
          <div className="absolute inset-0 grid place-items-center">
            <EmptyState title="Nothing open">
              <div className="space-y-1.5">
                <div>
                  <Kbd>⌘</Kbd> <Kbd>P</Kbd> go to file · <Kbd>⌘</Kbd> <Kbd>⇧</Kbd> <Kbd>F</Kbd> search
                </div>
                <div>
                  <Kbd>F12</Kbd> go to definition · <Kbd>⇧</Kbd> <Kbd>F12</Kbd> find references
                </div>
                <div>
                  <Kbd>⌘</Kbd> <Kbd>J</Kbd> terminal · <Kbd>⌘</Kbd> <Kbd>B</Kbd> sidebar
                </div>
              </div>
            </EmptyState>
          </div>
        )}
      </div>
    </div>
  );
}
