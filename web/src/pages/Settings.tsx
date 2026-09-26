import clsx from "clsx";
import { Check } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, SectionLabel, Segmented, Spinner } from "../components/ui";
import { api, type SettingsPayload } from "../lib/api";
import { usePageTitle } from "../lib/title";
import type { Settings } from "../lib/types";

const ROLES: { id: string; label: string; what: string }[] = [
  { id: "architect", label: "Architect", what: "designs each client's company and codebase" },
  { id: "implementer", label: "Implementer", what: "writes the code and test suite" },
  { id: "designer", label: "Exercise designer", what: "injects the bug, writes tickets, tours & questions" },
  { id: "writer", label: "Writer", what: "writes the incident thread in the team's voices" },
  { id: "reviewer", label: "Reviewer", what: "QA on each case + your debrief code reviews" },
  { id: "mentor", label: "Mentor", what: "the pair-programmer you chat with" },
  { id: "grader", label: "Grader", what: "checks recon answers" },
];

export default function SettingsPage() {
  usePageTitle("Settings");
  const [data, setData] = useState<SettingsPayload | null>(null);
  const [models, setModels] = useState<{ id: string; name: string; prompt: number; completion: number }[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.settings().then(setData);
    api.models().then(setModels).catch(() => {});
  }, []);

  if (!data) return <div className="grid h-[60vh] place-items-center"><Spinner className="size-6" /></div>;
  const s = data.settings;

  const save = async (patch: Partial<Settings> & { level?: number }) => {
    const r = await api.saveSettings(patch);
    setData({ ...data, settings: r.settings, learner: patch.level != null ? { level: patch.level } : data.learner });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1500);
  };

  const presetMatch = Object.entries(data.presets).find(([, m]) => ROLES.every((r) => m[r.id] === s.models[r.id]))?.[0];

  return (
    <div className="mx-auto max-w-[920px] px-6 py-10">
      <div className="flex items-center gap-3">
        <h1 className="font-serif text-[42px] leading-none text-fg-0">Settings</h1>
        {saved && <span className="inline-flex items-center gap-1 text-[12.5px] text-green"><Check className="size-3.5" /> saved</span>}
      </div>

      <Card className="mt-8 p-6">
        <SectionLabel>Budget</SectionLabel>
        <div className="mt-3 flex flex-wrap items-baseline gap-x-8 gap-y-2">
          <div>
            <div className="text-[30px] font-semibold text-fg-0">${data.budget.remaining?.toFixed(2) ?? "—"}</div>
            <div className="text-[12px] text-fg-2">left on your OpenRouter key{data.budget.limit ? ` (of $${data.budget.limit})` : ""}</div>
          </div>
          <div>
            <div className="text-[30px] font-semibold text-fg-0">${data.spend.total_usd.toFixed(2)}</div>
            <div className="text-[12px] text-fg-2">spent so far</div>
          </div>
        </div>
        {data.spend.by_role.length > 0 && (
          <table className="mt-5 w-full text-left text-[12.5px]">
            <thead className="text-fg-3">
              <tr>
                <th className="pb-2 font-medium">Role</th>
                <th className="pb-2 font-medium">Model</th>
                <th className="pb-2 text-right font-medium">Calls</th>
                <th className="pb-2 text-right font-medium">Cost</th>
              </tr>
            </thead>
            <tbody className="text-fg-1">
              {data.spend.by_role.map((r) => (
                <tr key={r.role + r.model} className="border-t border-line/60">
                  <td className="py-1.5">{r.role}</td>
                  <td className="py-1.5 font-mono text-[11.5px] text-fg-2">{r.model}</td>
                  <td className="py-1.5 text-right tabular-nums">{r.calls}</td>
                  <td className="py-1.5 text-right tabular-nums">${(r.cost ?? 0).toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="mt-5 flex flex-wrap items-center gap-6">
          <label className="flex items-center gap-2 text-[13px] text-fg-1" title="There's no login, so this caps what anyone (or a bug) can spend in a day">
            Daily AI budget
            <input type="number" min={0} step={1} defaultValue={s.daily_budget_usd} onBlur={(e) => void save({ daily_budget_usd: Number(e.target.value) })}
              className="w-20 rounded-md border border-line-strong bg-ink-0 px-2 py-1 text-fg-0 outline-none focus:border-blue" /> USD / 24h
          </label>
          <label className="flex items-center gap-2 text-[13px] text-fg-1">
            Pause background generation below
            <input type="number" min={0} step={0.5} defaultValue={s.budget_floor_usd} onBlur={(e) => void save({ budget_floor_usd: Number(e.target.value) })}
              className="w-20 rounded-md border border-line-strong bg-ink-0 px-2 py-1 text-fg-0 outline-none focus:border-blue" /> USD
          </label>
        </div>
      </Card>

      <Card className="mt-6 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SectionLabel>Models</SectionLabel>
          <Segmented
            value={presetMatch ?? "custom"}
            options={[
              { value: "max", label: "Max quality" },
              { value: "balanced", label: "Balanced" },
              { value: "economy", label: "Economy" },
              ...(presetMatch ? [] : [{ value: "custom", label: "Custom" }]),
            ]}
            onChange={(v) => v !== "custom" && void save({ models: data.presets[v] })}
          />
        </div>
        <p className="mt-2 text-[12.5px] text-fg-2">Any OpenRouter model can fill any role. Generation quality matters most for the architect, implementer, and designer.</p>
        <div className="mt-4 space-y-2.5">
          {ROLES.map((r) => (
            <div key={r.id} className="grid items-center gap-3 sm:grid-cols-[200px_1fr]">
              <div>
                <div className="text-[13px] text-fg-0">{r.label}</div>
                <div className="text-[11.5px] text-fg-3">{r.what}</div>
              </div>
              <select
                value={s.models[r.id]}
                onChange={(e) => void save({ models: { ...s.models, [r.id]: e.target.value } })}
                className="rounded-lg border border-line-strong bg-ink-0 px-2.5 py-1.5 font-mono text-[12px] text-fg-0 outline-none focus:border-blue"
              >
                {!models.some((m) => m.id === s.models[r.id]) && <option value={s.models[r.id]}>{s.models[r.id]}</option>}
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id}  ·  ${m.prompt.toFixed(2)} / ${m.completion.toFixed(2)} per M
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </Card>

      <Card className="mt-6 p-6">
        <SectionLabel>Practice</SectionLabel>
        <div className="mt-4 space-y-5">
          <Row label="Difficulty" hint="Adapts automatically after every task. Nudge it if it feels off.">
            <div className="flex items-center gap-3">
              <input type="range" min={1} max={10} step={0.5} defaultValue={data.learner.level} onMouseUp={(e) => void save({ level: Number((e.target as HTMLInputElement).value) })}
                className="w-48 accent-[#72b4ff]" />
              <span className="font-mono text-[12.5px] text-fg-1">{data.learner.level.toFixed(1)}</span>
            </div>
          </Row>
          <Row label="Default plan" hint="What's pre-selected on a client's briefing page.">
            <Segmented
              value={s.default_plan.includes("feature") ? "full" : "short"}
              options={[
                { value: "short", label: "Recon + incident" },
                { value: "full", label: "+ feature ticket" },
              ]}
              onChange={(v) => void save({ default_plan: v === "full" ? ["recon", "incident", "feature"] : ["recon", "incident"] })}
            />
          </Row>
          <Row label="Timer" hint="Countdown shows time left to par; stopwatch counts up.">
            <Segmented value={s.timer_mode} options={[{ value: "stopwatch", label: "Stopwatch" }, { value: "countdown", label: "Countdown" }]} onChange={(v) => void save({ timer_mode: v })} />
          </Row>
          <Row label="Inbox size" hint="Clients generated ahead of time so you never wait.">
            <Segmented value={String(s.buffer_size)} options={["1", "2", "3"].map((v) => ({ value: v, label: v }))} onChange={(v) => void save({ buffer_size: Number(v) })} />
          </Row>
          <Row label="Background generation" hint="Keep the inbox stocked automatically.">
            <Segmented value={s.auto_generate ? "on" : "off"} options={[{ value: "on", label: "On" }, { value: "off", label: "Off" }]} onChange={(v) => void save({ auto_generate: v === "on" })} />
          </Row>
          <Row label="Mentor's name" hint="Your pairing partner.">
            <input defaultValue={s.mentor_name} onBlur={(e) => e.target.value.trim() && void save({ mentor_name: e.target.value.trim() })}
              className="w-40 rounded-md border border-line-strong bg-ink-0 px-2.5 py-1.5 text-[13px] text-fg-0 outline-none focus:border-blue" />
          </Row>
        </div>
      </Card>
      {data.sandbox && (
        <Card className="mt-6 p-6">
          <SectionLabel>Sandbox</SectionLabel>
          <p className="mt-2 text-[13px] text-fg-2">
            Generated code, tests and your terminal run as an unprivileged user. Checked from inside the jail when the server started:
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {[
              ["Runs as", data.sandbox.uid === 0 ? "root" : `uid ${data.sandbox.uid}`, data.sandbox.uid !== 0],
              ["Server secrets", data.sandbox.server_environ === "blocked" ? "unreadable" : "READABLE", data.sandbox.server_environ === "blocked"],
              ["Network", data.sandbox.network === "blocked" ? "none" : "OPEN", data.sandbox.network === "blocked"],
            ].map(([label, value, ok]) => (
              <div key={String(label)} className="rounded-lg border border-line bg-ink-0 px-3 py-2">
                <div className="text-[11.5px] text-fg-3">{label}</div>
                <div className={clsx("mt-0.5 font-mono text-[13px]", ok ? "text-green" : "text-red")}>{value}</div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="grid items-center gap-3 sm:grid-cols-[200px_1fr]">
      <div>
        <div className="text-[13px] text-fg-0">{label}</div>
        <div className="text-[11.5px] text-fg-3">{hint}</div>
      </div>
      <div>{children}</div>
    </div>
  );
}
