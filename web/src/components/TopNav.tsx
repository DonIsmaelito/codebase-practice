import clsx from "clsx";
import { Settings } from "lucide-react";
import { useEffect } from "react";
import { Link, NavLink } from "react-router";
import { useDesk } from "../lib/desk";

const links = [
  { to: "/", label: "Desk", end: true },
  { to: "/atlas", label: "Atlas" },
  { to: "/journal", label: "Journal" },
  { to: "/progress", label: "Progress" },
  { to: "/playbook", label: "Playbook" },
];

export function Logo({ className }: { className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-2", className)}>
      <svg viewBox="0 0 32 32" className="size-6">
        <rect width="32" height="32" rx="8" fill="#141824" stroke="#2a3143" />
        <path d="M9 11l5 5-5 5" fill="none" stroke="#72b4ff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M16.5 21.5h7" stroke="#f5b454" strokeWidth="2.6" strokeLinecap="round" />
      </svg>
      <span className="font-serif text-[21px] leading-none tracking-tight text-fg-0">Cold Start</span>
    </span>
  );
}

export default function TopNav() {
  const { state, load } = useDesk();
  useEffect(() => {
    if (!state) void load();
  }, [state, load]);
  const budget = state?.budget;
  const remaining = budget?.ok && budget.remaining != null ? budget.remaining : null;

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-ink-0/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-[1280px] items-center gap-8 px-6">
        <Link to="/" className="shrink-0">
          <Logo />
        </Link>
        <nav className="flex items-center gap-1">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                clsx(
                  "rounded-md px-2.5 py-1.5 text-[13.5px] transition-colors",
                  isActive ? "bg-ink-3 text-fg-0" : "text-fg-2 hover:text-fg-0",
                )
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          {state?.active && (
            <Link
              to={`/e/${state.active.id}`}
              className="group inline-flex items-center gap-2 rounded-full border border-amber/30 bg-amber-dim px-3 py-1 text-[12.5px] text-amber"
            >
              <span className="size-1.5 animate-breathe rounded-full bg-amber" />
              Back to {state.active.company}
            </Link>
          )}
          {remaining != null && (
            <span
              className={clsx(
                "rounded-full border px-2.5 py-0.5 font-mono text-[11.5px]",
                remaining < 5 ? "border-red/30 text-red" : "border-line text-fg-2",
              )}
              title="Remaining OpenRouter credit"
            >
              ${remaining.toFixed(2)}
            </span>
          )}
          <NavLink
            to="/settings"
            className={({ isActive }) => clsx("rounded-md p-1.5 transition-colors", isActive ? "bg-ink-3 text-fg-0" : "text-fg-2 hover:text-fg-0")}
            title="Settings"
          >
            <Settings className="size-4" />
          </NavLink>
        </div>
      </div>
    </header>
  );
}
