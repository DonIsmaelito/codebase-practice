// The live side of a task: polling for the incident thread and coach check-ins.
import { useEffect } from "react";
import type { EngagementPayload } from "../lib/types";
import { useWB } from "./store";

const muteKey = (taskId: string) => `cs-coach-muted-${taskId}`;

export function coachMuted(taskId: string): boolean {
  try {
    return localStorage.getItem(muteKey(taskId)) === "1";
  } catch {
    return false;
  }
}

export function muteCoach(taskId: string): void {
  try {
    localStorage.setItem(muteKey(taskId), "1");
  } catch {
    /* private mode: muted until reload */
  }
}

/** The task with a live side right now: the one you're on, or the incident you just
 *  finished (its thread stays open until you move on). */
export function liveTaskId(data: EngagementPayload): string | null {
  if (data.engagement.status !== "active") return null;
  const active = Object.values(data.tasks).find((t) => t.status === "active");
  if (active) return active.kind === "recon" ? null : active.id;
  const inc = data.tasks.incident;
  return inc.status === "passed" || inc.status === "revealed" ? inc.id : null;
}

export function useLivePulse(data: EngagementPayload): void {
  const taskId = liveTaskId(data);
  const coachOn = data.settings.coach_nudges !== false;
  useEffect(() => {
    if (!taskId) return;
    let alive = true;
    let timer = 0;
    const loop = async () => {
      await useWB.getState().pollLive(taskId, coachOn && !coachMuted(taskId));
      if (!alive) return;
      const { live } = useWB.getState();
      const waiting = live.typing !== null || (live.thread.at(-1)?.kind === "learner" && !live.replyError);
      timer = window.setTimeout(() => void loop(), waiting ? 2000 : document.hidden ? 30000 : 12000);
    };
    void loop();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [taskId, coachOn]);
}
