// Monaco setup: workers, the Cold Start theme, and Python intelligence backed
// by jedi on the server (definition, references, hover, outline).
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
import CssWorker from "monaco-editor/language/css/css.worker?worker";
import HtmlWorker from "monaco-editor/language/html/html.worker?worker";
import JsonWorker from "monaco-editor/language/json/json.worker?worker";
import TsWorker from "monaco-editor/language/typescript/ts.worker?worker";
import { api } from "./api";
import { languageFor } from "./format";
import type { Location } from "./types";

export { monaco };

self.MonacoEnvironment = {
  getWorker(_id: string, label: string) {
    if (label === "json") return new JsonWorker();
    if (label === "css" || label === "scss" || label === "less") return new CssWorker();
    if (label === "html" || label === "handlebars" || label === "razor") return new HtmlWorker();
    if (label === "typescript" || label === "javascript") return new TsWorker();
    return new EditorWorker();
  },
};

loader.config({ monaco });

export const THEME = "coldstart-night";

monaco.editor.defineTheme(THEME, {
  base: "vs-dark",
  inherit: true,
  rules: [
    { token: "", foreground: "D5DAE5" },
    { token: "comment", foreground: "5E687D", fontStyle: "italic" },
    { token: "keyword", foreground: "C4A2FF" },
    { token: "string", foreground: "A3D9A5" },
    { token: "string.escape", foreground: "7FD8CC" },
    { token: "number", foreground: "F5B870" },
    { token: "type", foreground: "7CC4FF" },
    { token: "identifier", foreground: "D5DAE5" },
    { token: "delimiter", foreground: "8A93A6" },
    { token: "operator", foreground: "8FD5E8" },
    { token: "tag", foreground: "7CC4FF" },
    { token: "attribute.name", foreground: "F5B870" },
    { token: "attribute.value", foreground: "A3D9A5" },
    { token: "key", foreground: "7CC4FF" },
    { token: "predefined", foreground: "7FD8CC" },
  ],
  colors: {
    "editor.background": "#0E1118",
    "editor.foreground": "#D5DAE5",
    "editorLineNumber.foreground": "#3A4254",
    "editorLineNumber.activeForeground": "#8A93A6",
    "editor.lineHighlightBackground": "#141824",
    "editor.lineHighlightBorder": "#00000000",
    "editor.selectionBackground": "#2A3A5A",
    "editor.inactiveSelectionBackground": "#1E2A40",
    "editorCursor.foreground": "#72B4FF",
    "editorIndentGuide.background1": "#1A1F2B",
    "editorIndentGuide.activeBackground1": "#2A3143",
    "editorWidget.background": "#131722",
    "editorWidget.border": "#2A3143",
    "editorHoverWidget.background": "#131722",
    "editorHoverWidget.border": "#2A3143",
    "editorSuggestWidget.background": "#131722",
    "editorSuggestWidget.border": "#2A3143",
    "editorSuggestWidget.selectedBackground": "#212839",
    "peekView.border": "#72B4FF",
    "peekViewEditor.background": "#0B0E15",
    "peekViewResult.background": "#0F121A",
    "peekViewTitle.background": "#131722",
    "peekViewResult.selectionBackground": "#212839",
    "scrollbarSlider.background": "#21283980",
    "scrollbarSlider.hoverBackground": "#2A3143",
    "scrollbarSlider.activeBackground": "#343d52",
    "minimap.background": "#0E1118",
    "diffEditor.insertedTextBackground": "#56D6A426",
    "diffEditor.removedTextBackground": "#F0717826",
    "diffEditor.insertedLineBackground": "#56D6A412",
    "diffEditor.removedLineBackground": "#F0717812",
    "editorGutter.background": "#0E1118",
    "editorBracketMatch.background": "#72B4FF22",
    "editorBracketMatch.border": "#72B4FF55",
    "editor.findMatchBackground": "#F5B45455",
    "editor.findMatchHighlightBackground": "#F5B45428",
    "editor.wordHighlightBackground": "#72B4FF1E",
    "editor.wordHighlightStrongBackground": "#72B4FF2A",
    "editorOverviewRuler.border": "#00000000",
    "focusBorder": "#72B4FF66",
    "input.background": "#0E1118",
    "input.border": "#2A3143",
    "list.hoverBackground": "#191E2B",
    "list.activeSelectionBackground": "#212839",
    "quickInput.background": "#131722",
  },
});
monaco.editor.setTheme(THEME);

export async function colorize(code: string, lang: string): Promise<string> {
  return monaco.editor.colorize(code, lang, { tabSize: 4 });
}

// --- model URIs --------------------------------------------------------------------------
// Workspace files:  file:///ws/<relative path>
// Library sources:  file:///ext/<absolute path>   (read-only)

export function modelUri(path: string, external = false): monaco.Uri {
  return external
    ? monaco.Uri.from({ scheme: "file", path: `/ext${path}` })
    : monaco.Uri.from({ scheme: "file", path: `/ws/${path}` });
}

export function pathFromUri(uri: monaco.Uri): { path: string; external: boolean } | null {
  if (uri.path.startsWith("/ws/")) return { path: uri.path.slice(4), external: false };
  if (uri.path.startsWith("/ext/")) return { path: uri.path.slice(4), external: true };
  return null;
}

export function getModel(path: string, external = false): monaco.editor.ITextModel | null {
  return monaco.editor.getModel(modelUri(path, external));
}

export function createModel(path: string, content: string, external = false): monaco.editor.ITextModel {
  const existing = getModel(path, external);
  if (existing) return existing;
  return monaco.editor.createModel(content, languageFor(path), modelUri(path, external));
}

export function disposeAllModels(): void {
  for (const m of monaco.editor.getModels()) m.dispose();
}

// --- intelligence context -----------------------------------------------------------------

interface IntelContext {
  eid: string;
  open: (path: string, external: boolean, line?: number, column?: number) => void;
  log: (kind: string, data: Record<string, unknown>) => void;
}

let ctx: IntelContext | null = null;
export function setIntelContext(next: IntelContext | null) {
  ctx = next;
}

async function ensureModel(loc: { path: string; external: boolean }): Promise<monaco.editor.ITextModel | null> {
  if (!ctx) return null;
  const existing = getModel(loc.path, loc.external);
  if (existing) return existing;
  try {
    const { content } = loc.external ? await api.external(loc.path) : await api.readFile(ctx.eid, loc.path);
    return createModel(loc.path, content, loc.external);
  } catch {
    return null;
  }
}

function toMonacoLocation(l: Location): monaco.languages.Location {
  return {
    uri: modelUri(l.path, l.external),
    range: new monaco.Range(l.line, l.column, l.line, l.column + Math.max(1, l.name.length)),
  };
}

let registered = false;
export function registerPythonIntel() {
  if (registered) return;
  registered = true;

  monaco.languages.registerDefinitionProvider("python", {
    async provideDefinition(model, position) {
      const where = pathFromUri(model.uri);
      if (!ctx || !where || where.external) return null;
      const locs = await api.definition(ctx.eid, where.path, position.lineNumber, position.column, model.getValue());
      await Promise.all(locs.map(ensureModel));
      const word = model.getWordAtPosition(position)?.word;
      if (locs[0]) ctx.log("definition", { name: word, target: `${locs[0].path}:${locs[0].line}`, external: locs[0].external });
      return locs.map(toMonacoLocation);
    },
  });

  monaco.languages.registerReferenceProvider("python", {
    async provideReferences(model, position) {
      const where = pathFromUri(model.uri);
      if (!ctx || !where || where.external) return [];
      const locs = await api.references(ctx.eid, where.path, position.lineNumber, position.column, model.getValue());
      await Promise.all([...new Map(locs.map((l) => [l.path, l])).values()].map(ensureModel));
      ctx.log("references", { name: model.getWordAtPosition(position)?.word, count: locs.length });
      return locs.map(toMonacoLocation);
    },
  });

  monaco.languages.registerHoverProvider("python", {
    async provideHover(model, position) {
      const where = pathFromUri(model.uri);
      const word = model.getWordAtPosition(position);
      if (!ctx || !where || where.external || !word) return null;
      const h = await api.hover(ctx.eid, where.path, position.lineNumber, position.column, model.getValue());
      if (!h) return null;
      const contents: monaco.IMarkdownString[] = [];
      const sig = h.signatures[0] ?? `${h.type} ${h.name}`;
      contents.push({ value: "```python\n" + sig + "\n```" });
      if (h.doc) contents.push({ value: h.doc.length > 1200 ? h.doc.slice(0, 1200) + "…" : h.doc });
      if (h.module && h.module !== "__main__") contents.push({ value: `*${h.module}*` });
      return {
        range: new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn),
        contents,
      };
    },
  });

  monaco.languages.registerDocumentSymbolProvider("python", {
    async provideDocumentSymbols(model) {
      const where = pathFromUri(model.uri);
      if (!ctx || !where || where.external) return [];
      const syms = await api.symbols(ctx.eid, where.path);
      return syms.map((s) => {
        const line = model.getLineContent(Math.min(s.line, model.getLineCount()));
        const range = new monaco.Range(s.line, 1, s.line, line.length + 1);
        return {
          name: s.name,
          detail: s.parent ? `in ${s.parent}` : "",
          kind: s.type === "class" ? monaco.languages.SymbolKind.Class : s.parent ? monaco.languages.SymbolKind.Method : monaco.languages.SymbolKind.Function,
          range,
          selectionRange: range,
          tags: [],
          containerName: s.parent ?? undefined,
        };
      });
    },
  });

  // Cross-file navigation (Cmd+click, F12, peek → open) lands in our tab system.
  monaco.editor.registerEditorOpener({
    openCodeEditor(_source, resource, selectionOrPosition) {
      const where = pathFromUri(resource);
      if (!ctx || !where) return false;
      let line: number | undefined;
      let column: number | undefined;
      if (selectionOrPosition) {
        if ("lineNumber" in selectionOrPosition) {
          line = selectionOrPosition.lineNumber;
          column = selectionOrPosition.column;
        } else {
          line = selectionOrPosition.startLineNumber;
          column = selectionOrPosition.startColumn;
        }
      }
      ctx.open(where.path, where.external, line, column);
      return true;
    },
  });
}
