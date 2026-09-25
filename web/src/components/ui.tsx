import clsx from "clsx";
import { Loader2 } from "lucide-react";
import { type ButtonHTMLAttributes, type ReactNode, memo, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { hashHue, initials } from "../lib/format";

type Tone = "neutral" | "blue" | "amber" | "violet" | "green" | "red" | "teal";

const toneBtn: Record<Tone, string> = {
  neutral: "bg-ink-3 hover:bg-ink-4 text-fg-0 border-line-strong",
  blue: "bg-blue text-ink-0 hover:brightness-110 border-transparent",
  amber: "bg-amber text-ink-0 hover:brightness-110 border-transparent",
  violet: "bg-violet text-ink-0 hover:brightness-110 border-transparent",
  green: "bg-green text-ink-0 hover:brightness-110 border-transparent",
  red: "bg-red text-ink-0 hover:brightness-110 border-transparent",
  teal: "bg-teal text-ink-0 hover:brightness-110 border-transparent",
};

export function Button({
  tone = "neutral",
  size = "md",
  ghost,
  loading,
  icon,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: Tone;
  size?: "sm" | "md" | "lg";
  ghost?: boolean;
  loading?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg border font-medium transition-all select-none",
        "disabled:opacity-50 active:scale-[0.98]",
        size === "sm" && "h-7 px-2.5 text-[12.5px]",
        size === "md" && "h-9 px-3.5 text-[13.5px]",
        size === "lg" && "h-11 px-5 text-[15px]",
        ghost ? "border-transparent bg-transparent text-fg-1 hover:bg-ink-3 hover:text-fg-0" : toneBtn[tone],
        className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

const toneChip: Record<Tone, string> = {
  neutral: "bg-ink-3 text-fg-1 border-line",
  blue: "bg-blue-dim text-blue border-blue/20",
  amber: "bg-amber-dim text-amber border-amber/20",
  violet: "bg-violet-dim text-violet border-violet/20",
  green: "bg-green-dim text-green border-green/20",
  red: "bg-red-dim text-red border-red/20",
  teal: "bg-teal-dim text-teal border-teal/20",
};

export function Chip({ tone = "neutral", children, className, mono }: { tone?: Tone; children: ReactNode; className?: string; mono?: boolean }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-[1px] text-[11.5px] leading-[18px] whitespace-nowrap",
        mono && "font-mono text-[11px]",
        toneChip[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-line-strong bg-ink-2 px-1 font-mono text-[10.5px] text-fg-2">{children}</kbd>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("size-4 animate-spin text-fg-2", className)} />;
}

export function Monogram({ name, size = 40, className }: { name: string; size?: number; className?: string }) {
  const hue = hashHue(name);
  return (
    <div
      className={clsx("grid shrink-0 place-items-center rounded-xl font-semibold tracking-tight text-white/95", className)}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        background: `linear-gradient(135deg, oklch(0.58 0.13 ${hue}), oklch(0.38 0.1 ${(hue + 40) % 360}))`,
        boxShadow: `inset 0 1px 0 rgba(255,255,255,0.14), 0 6px 20px -8px oklch(0.5 0.14 ${hue} / 0.6)`,
      }}
    >
      {initials(name)}
    </div>
  );
}

export function Avatar({ name, size = 28 }: { name: string; size?: number }) {
  const hue = hashHue(name + "·");
  return (
    <div
      className="grid shrink-0 place-items-center rounded-full font-semibold text-white/90"
      style={{ width: size, height: size, fontSize: size * 0.4, background: `oklch(0.45 0.09 ${hue})` }}
      title={name}
    >
      {initials(name)}
    </div>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("rounded-2xl border border-line bg-ink-1", className)}>{children}</div>;
}

export function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx("text-[11px] font-semibold tracking-[0.08em] text-fg-2 uppercase", className)}>{children}</div>
  );
}

export function ProgressBar({ value, tone = "blue", className }: { value: number; tone?: Tone; className?: string }) {
  const color = { neutral: "bg-fg-2", blue: "bg-blue", amber: "bg-amber", violet: "bg-violet", green: "bg-green", red: "bg-red", teal: "bg-teal" }[tone];
  return (
    <div className={clsx("h-1 overflow-hidden rounded-full bg-ink-3", className)}>
      <div className={clsx("h-full rounded-full transition-[width] duration-700", color)} style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  className,
}: {
  value: T;
  options: { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  className?: string;
}) {
  return (
    <div className={clsx("inline-flex rounded-lg border border-line bg-ink-1 p-0.5", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "rounded-md px-2.5 py-1 text-[12.5px] transition-colors",
            o.value === value ? "bg-ink-4 text-fg-0" : "text-fg-2 hover:text-fg-1",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

// --- Markdown with editor-grade code highlighting --------------------------------------

let colorizer: Promise<(code: string, lang: string) => Promise<string>> | null = null;
function getColorizer() {
  colorizer ??= import("../lib/monaco").then((m) => m.colorize);
  return colorizer;
}

const CodeBlock = memo(function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [html, setHtml] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const language = { py: "python", python: "python", diff: "plaintext", bash: "shell", sh: "shell", text: "plaintext" }[lang] ?? lang;
    if (!["python", "json", "yaml", "shell", "sql", "ini", "markdown"].includes(language)) return;
    getColorizer()
      .then((fn) => fn(code, language))
      .then((h) => alive && setHtml(h))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [code, lang]);
  if (lang === "diff") {
    return (
      <pre>
        <code>
          {code.split("\n").map((l, i) => (
            <div
              key={i}
              className={clsx(
                l.startsWith("+") && !l.startsWith("+++") && "text-green",
                l.startsWith("-") && !l.startsWith("---") && "text-red",
                l.startsWith("@@") && "text-blue",
              )}
            >
              {l || " "}
            </div>
          ))}
        </code>
      </pre>
    );
  }
  return (
    <pre>
      {html ? <code dangerouslySetInnerHTML={{ __html: html }} /> : <code>{code}</code>}
    </pre>
  );
});

export const Markdown = memo(function Markdown({ children, className, large }: { children: string; className?: string; large?: boolean }) {
  return (
    <div className={clsx("prose-cs", large && "prose-lg", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ className: cls, children: kids, ...props }) {
            const match = /language-(\w+)/.exec(cls || "");
            const text = String(kids ?? "");
            if (match || text.includes("\n")) {
              return <CodeBlock code={text.replace(/\n$/, "")} lang={match?.[1] ?? "text"} />;
            }
            return (
              <code className={cls} {...props}>
                {kids}
              </code>
            );
          },
          pre({ children: kids }) {
            return <>{kids}</>;
          },
          a({ href, children: kids }) {
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {kids}
              </a>
            );
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
});

export function EmptyState({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      {icon && <div className="text-fg-3">{icon}</div>}
      <div className="text-[14px] font-medium text-fg-1">{title}</div>
      {children && <div className="max-w-sm text-[13px] text-fg-2">{children}</div>}
    </div>
  );
}
