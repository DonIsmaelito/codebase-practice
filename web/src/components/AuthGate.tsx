import { motion } from "motion/react";
import { Lock, Mail } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { authClient, authHeaders, loadConfig, signOut } from "../lib/auth";
import { Logo } from "./TopNav";
import { Button, Spinner } from "./ui";

type GateState = { kind: "loading" } | { kind: "open" } | { kind: "signed-out" } | { kind: "denied"; message: string };

/** Hosted mode: nothing renders until you're signed in with an allowed account. */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>({ kind: "loading" });

  const check = useCallback(async () => {
    const cfg = await loadConfig();
    if (!cfg.auth) return setState({ kind: "open" });
    const { data } = await authClient()!.auth.getCurrentUser();
    if (!data?.user) return setState({ kind: "signed-out" });
    const res = await fetch("/api/state", { headers: await authHeaders() });
    if (res.ok) return setState({ kind: "open" });
    if (res.status === 403) {
      const body = await res.json().catch(() => ({}));
      return setState({ kind: "denied", message: body.detail ?? "This account doesn't have access." });
    }
    setState({ kind: "signed-out" });
  }, []);

  useEffect(() => {
    void check();
    const onUnauthorized = () => setState({ kind: "signed-out" });
    window.addEventListener("coldstart:unauthorized", onUnauthorized);
    return () => window.removeEventListener("coldstart:unauthorized", onUnauthorized);
  }, [check]);

  if (state.kind === "open") return <>{children}</>;
  if (state.kind === "loading") {
    return (
      <div className="surface-glow grid h-full place-items-center">
        <Spinner className="size-6" />
      </div>
    );
  }
  return (
    <div className="surface-glow grid h-full place-items-center px-6">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="w-[420px] max-w-full">
        <Logo />
        {state.kind === "denied" ? <Denied message={state.message} /> : <SignIn onSignedIn={check} />}
      </motion.div>
    </div>
  );
}

function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const client = authClient()!;

  const oauth = async (provider: "google" | "github") => {
    setBusy(provider);
    setError(null);
    const { error: err } = await client.auth.signInWithOAuth(provider, { redirectTo: `${window.location.origin}/` });
    if (err) {
      setError(err.message);
      setBusy(null);
    }
  };

  const sendCode = async () => {
    if (!email.trim()) return;
    setBusy("email");
    setError(null);
    const { error: err } = await client.auth.signInWithOtp({ email: email.trim() });
    setBusy(null);
    if (err) setError(err.message);
    else setSent(true);
  };

  const verify = async () => {
    if (!code.trim()) return;
    setBusy("verify");
    setError(null);
    const { error: err } = await client.auth.verifyOtp({ email: email.trim(), otp: code.trim() });
    setBusy(null);
    if (err) setError(err.message);
    else onSignedIn();
  };

  return (
    <div className="mt-8">
      <h1 className="font-serif text-[40px] leading-[1.05] text-fg-0">Clock in.</h1>
      <p className="mt-2 text-[14px] leading-relaxed text-fg-1">
        Your clients, codebases, and progress live in the cloud now. Sign in to pick up where you left off.
      </p>
      <div className="mt-7 space-y-2.5">
        <Button className="w-full" size="lg" loading={busy === "google"} onClick={() => void oauth("google")}
          icon={<svg viewBox="0 0 24 24" className="size-4"><path fill="#4285F4" d="M22.5 12.3c0-.8-.1-1.5-.2-2.3H12v4.3h5.9a5 5 0 0 1-2.2 3.3v2.8h3.5c2.1-1.9 3.3-4.8 3.3-8.1z"/><path fill="#34A853" d="M12 23c3 0 5.5-1 7.3-2.7l-3.5-2.8c-1 .7-2.3 1.1-3.8 1.1-2.9 0-5.4-2-6.3-4.7H2.1v2.9A11 11 0 0 0 12 23z"/><path fill="#FBBC05" d="M5.7 13.9a6.6 6.6 0 0 1 0-4.2V6.8H2.1a11 11 0 0 0 0 9.9l3.6-2.8z"/><path fill="#EA4335" d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.2-3.2A11 11 0 0 0 2.1 6.8l3.6 2.9C6.6 7.4 9.1 5.4 12 5.4z"/></svg>}>
          Continue with Google
        </Button>
        <Button className="w-full" size="lg" loading={busy === "github"} onClick={() => void oauth("github")} icon={<svg viewBox="0 0 24 24" className="size-4" fill="currentColor"><path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.52-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.42-2.7 5.39-5.26 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5z"/></svg>}>
          Continue with GitHub
        </Button>
      </div>
      <div className="my-6 flex items-center gap-3 text-[11.5px] tracking-wide text-fg-3 uppercase">
        <span className="h-px flex-1 bg-line" /> or an emailed code <span className="h-px flex-1 bg-line" />
      </div>
      {!sent ? (
        <div className="flex gap-2">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void sendCode()}
            placeholder="you@example.com"
            className="min-w-0 flex-1 rounded-lg border border-line-strong bg-ink-1 px-3 text-[14px] text-fg-0 outline-none placeholder:text-fg-3 focus:border-blue"
          />
          <Button tone="blue" loading={busy === "email"} icon={<Mail className="size-4" />} onClick={() => void sendCode()}>
            Send code
          </Button>
        </div>
      ) : (
        <div>
          <p className="mb-2 text-[13px] text-fg-2">We sent a 6-digit code to {email}. It expires in 5 minutes.</p>
          <div className="flex gap-2">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              onKeyDown={(e) => e.key === "Enter" && void verify()}
              inputMode="numeric"
              autoFocus
              placeholder="123456"
              className="min-w-0 flex-1 rounded-lg border border-line-strong bg-ink-1 px-3 font-mono text-[16px] tracking-[0.3em] text-fg-0 outline-none placeholder:text-fg-3 focus:border-blue"
            />
            <Button tone="blue" loading={busy === "verify"} onClick={() => void verify()}>
              Sign in
            </Button>
          </div>
          <button className="mt-2 text-[12px] text-fg-3 hover:text-fg-1" onClick={() => { setSent(false); setCode(""); }}>
            Use a different email
          </button>
        </div>
      )}
      {error && <div className="mt-4 rounded-lg border border-red/25 bg-red-dim/30 px-3 py-2 text-[12.5px] text-red">{error}</div>}
    </div>
  );
}

function Denied({ message }: { message: string }) {
  return (
    <div className="mt-8">
      <div className="flex items-center gap-2 text-amber">
        <Lock className="size-4" />
        <span className="text-[12px] font-semibold tracking-[0.1em] uppercase">Private</span>
      </div>
      <h1 className="mt-2 font-serif text-[36px] leading-[1.1] text-fg-0">This Cold Start is someone else's.</h1>
      <p className="mt-3 text-[14px] leading-relaxed text-fg-1">{message}</p>
      <Button className="mt-6" onClick={() => void signOut()}>
        Sign out
      </Button>
    </div>
  );
}
