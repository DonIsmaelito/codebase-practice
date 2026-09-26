// Hosted mode: InsForge Auth in front of everything. Locally the server says
// auth is off and none of this runs.
import { createClient, type InsForgeClient } from "@insforge/sdk";

export interface PublicConfig {
  auth: boolean;
  insforgeUrl: string | null;
  anonKey: string | null;
}

let config: PublicConfig | null = null;
let client: InsForgeClient | null = null;
let loading: Promise<PublicConfig> | null = null;

export function loadConfig(): Promise<PublicConfig> {
  loading ??= fetch("/api/public-config")
    .then((r) => r.json() as Promise<PublicConfig>)
    .then((cfg) => {
      config = cfg;
      if (cfg.auth && cfg.insforgeUrl && cfg.anonKey) {
        // The constructor also finishes an OAuth redirect (?insforge_code=…) if present.
        client = createClient({ baseUrl: cfg.insforgeUrl, anonKey: cfg.anonKey });
      }
      return cfg;
    });
  return loading;
}

export function authEnabled(): boolean {
  return !!config?.auth;
}

export function authClient(): InsForgeClient | null {
  return client;
}

export async function accessToken(): Promise<string | null> {
  if (!client) return null;
  return client.getHttpClient().getValidAccessToken();
}

export async function authHeaders(): Promise<Record<string, string>> {
  const token = await accessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Tell the auth gate the server rejected our session (expired or signed out elsewhere). */
export function reportUnauthorized(): void {
  window.dispatchEvent(new Event("coldstart:unauthorized"));
}

export async function signOut(): Promise<void> {
  await client?.auth.signOut();
  window.location.assign("/");
}
