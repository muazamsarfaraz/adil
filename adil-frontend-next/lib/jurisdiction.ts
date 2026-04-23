import { JurisdictionEnum, type Jurisdiction } from "./types";

const COOKIE = "askadil_jurisdiction";
const MAX_AGE_S = 60 * 60 * 24 * 365;

// Server-side cookie reader lives in jurisdiction.server.ts (not yet needed — v1 reads client-side only).

export function readJurisdictionClient(): Jurisdiction | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`));
  if (!match) return null;
  const parsed = JurisdictionEnum.safeParse(decodeURIComponent(match[1]));
  return parsed.success ? parsed.data : null;
}

export function writeJurisdictionClient(j: Jurisdiction): void {
  if (typeof document === "undefined") return;
  document.cookie = `${COOKIE}=${encodeURIComponent(j)}; Path=/; Max-Age=${MAX_AGE_S}; SameSite=Lax`;
}
