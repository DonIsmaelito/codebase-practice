import { FitAddon } from "@xterm/addon-fit";
import { Terminal as XTerm } from "@xterm/xterm";
import { RotateCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { findRefs } from "./links";
import { useWB } from "./store";

const THEME = {
  background: "#0e1118",
  foreground: "#d5dae5",
  cursor: "#72b4ff",
  cursorAccent: "#0e1118",
  selectionBackground: "#2a3a5a",
  black: "#1a1f2d",
  red: "#f07178",
  green: "#56d6a4",
  yellow: "#f5b454",
  blue: "#72b4ff",
  magenta: "#c4a2ff",
  cyan: "#4fd6c8",
  white: "#d5dae5",
  brightBlack: "#5e687d",
  brightRed: "#ff8b92",
  brightGreen: "#7ee8bd",
  brightYellow: "#ffcb7a",
  brightBlue: "#9ccbff",
  brightMagenta: "#d7bfff",
  brightCyan: "#7fe8dc",
  brightWhite: "#ffffff",
};

export default function Terminal({ visible }: { visible: boolean }) {
  const eid = useWB((s) => s.eid);
  const hostRef = useRef<HTMLDivElement>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const [session, setSession] = useState(0);
  const [closed, setClosed] = useState(false);

  useEffect(() => {
    if (!eid || !hostRef.current) return;
    const term = new XTerm({
      theme: THEME,
      fontFamily: '"JetBrains Mono Variable", ui-monospace, Menlo, monospace',
      fontSize: 12.5,
      lineHeight: 1.25,
      cursorBlink: true,
      scrollback: 5000,
      allowProposedApi: true,
      macOptionIsMeta: true,
    });
    const fit = new FitAddon();
    fitRef.current = fit;
    term.loadAddon(fit);
    term.open(hostRef.current);
    try {
      fit.fit();
    } catch {
      /* host not measured yet */
    }

    // Clickable file:line references (tracebacks, pytest output).
    term.registerLinkProvider({
      provideLinks(y, callback) {
        const line = term.buffer.active.getLine(y - 1)?.translateToString(true) ?? "";
        const known = new Set(useWB.getState().tree.filter((e) => e.type === "file").map((e) => e.path));
        const refs = findRefs(line, known);
        callback(
          refs.map((r) => ({
            range: { start: { x: r.start + 1, y }, end: { x: r.end, y } },
            text: line.slice(r.start, r.end),
            decorations: { underline: true, pointerCursor: true },
            activate: () => void useWB.getState().openFile(r.path, false, r.line, 1, "flash"),
          })),
        );
      },
    });

    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/api/ws/${eid}/terminal?cols=${term.cols}&rows=${term.rows}`);
    ws.onmessage = (ev) => term.write(typeof ev.data === "string" ? ev.data : "");
    ws.onclose = () => {
      term.write("\r\n\x1b[38;5;245m[session closed]\x1b[0m\r\n");
      setClosed(true);
    };
    const onData = term.onData((d) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ t: "i", d })));
    const onResize = term.onResize(({ cols, rows }) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ t: "r", c: cols, r: rows })));
    const ro = new ResizeObserver(() => {
      try {
        fit.fit();
      } catch {
        /* hidden */
      }
    });
    ro.observe(hostRef.current);
    setClosed(false);
    return () => {
      ro.disconnect();
      onData.dispose();
      onResize.dispose();
      ws.close();
      term.dispose();
    };
  }, [eid, session]);

  useEffect(() => {
    if (visible) {
      const id = window.setTimeout(() => {
        try {
          fitRef.current?.fit();
        } catch {
          /* ignore */
        }
      }, 30);
      return () => window.clearTimeout(id);
    }
  }, [visible]);

  return (
    <div className="relative h-full">
      <div ref={hostRef} className="h-full" />
      {closed && (
        <button
          onClick={() => setSession((s) => s + 1)}
          className="absolute top-2 right-3 inline-flex items-center gap-1 rounded-md border border-line-strong bg-ink-2 px-2 py-1 text-[12px] text-fg-1 hover:text-fg-0"
        >
          <RotateCw className="size-3" /> New shell
        </button>
      )}
    </div>
  );
}
