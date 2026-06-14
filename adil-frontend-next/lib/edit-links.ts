// Magic-link + firm-session crypto for the solicitor listing-management flow.
//
// Ported from the sibling MCB project `mcb-ai-agm-ready-reckoner`
// (lib/edit-links.js + lib/admin-auth.js), adapted to TypeScript and a
// DEDICATED `EDIT_LINK_SECRET` (decoupled from any admin password).
//
// Stateless HMAC tokens — no token store needed. Two purposes, two derived
// secrets (domain separation, so a magic-link token can't be replayed as a
// session cookie):
//   • edit-link.v1   — the 7-day magic link emailed to the firm
//   • firm-session.v1 — the 24h HttpOnly session cookie set after a link is used
//
// Server-only: import this from route handlers / server components only, never
// from a Client Component.

import crypto from "crypto";

export const EDIT_LINK_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days
export const FIRM_SESSION_TTL_MS = 24 * 60 * 60 * 1000; // 24h
export const FIRM_COOKIE = "adil_firm";

export interface FirmClaims {
  slug: string; // the firm's SRA ID
  email: string;
  exp: number;
}

function secret(purpose: string): Buffer {
  const base = process.env.EDIT_LINK_SECRET;
  if (!base) throw new Error("EDIT_LINK_SECRET is not configured (server-side secret)");
  return crypto.createHash("sha256").update(`${base}.adil-listing.${purpose}`).digest();
}

function mint(purpose: string, slug: string, email: string, expMs: number): string {
  const payload = JSON.stringify({ s: slug, e: email.toLowerCase(), x: expMs });
  const payloadB64 = Buffer.from(payload).toString("base64url");
  const sig = crypto.createHmac("sha256", secret(purpose)).update(payloadB64).digest("base64url");
  return `${payloadB64}.${sig}`;
}

function verify(
  purpose: string,
  token: string | undefined | null,
): { valid: boolean; expired?: boolean; claims?: FirmClaims } {
  if (!token || typeof token !== "string") return { valid: false };
  const dot = token.indexOf(".");
  if (dot < 0) return { valid: false };
  const payloadB64 = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expected = crypto.createHmac("sha256", secret(purpose)).update(payloadB64).digest("base64url");
  if (sig.length !== expected.length) return { valid: false };
  try {
    if (!crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))) return { valid: false };
  } catch {
    return { valid: false };
  }
  let payload: { s?: string; e?: string; x?: number };
  try {
    payload = JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
  } catch {
    return { valid: false };
  }
  const slug = payload?.s;
  const email = payload?.e;
  const exp = payload?.x;
  if (!slug || !email || !Number.isFinite(exp)) return { valid: false };
  if ((exp as number) < Date.now()) return { valid: false, expired: true };
  return { valid: true, claims: { slug, email, exp: exp as number } };
}

// --- Magic link (emailed to the firm) ---
export function mintEditToken(slug: string, email: string, expMs = Date.now() + EDIT_LINK_TTL_MS): string {
  return mint("edit-link.v1", slug, email, expMs);
}
export function verifyEditToken(token: string | undefined | null) {
  return verify("edit-link.v1", token);
}

// --- Firm session (HttpOnly cookie set after a magic link is used) ---
export function signFirmSession(slug: string, email: string, expMs = Date.now() + FIRM_SESSION_TTL_MS): string {
  return mint("firm-session.v1", slug, email, expMs);
}
export function verifyFirmSession(cookieValue: string | undefined | null) {
  return verify("firm-session.v1", cookieValue);
}

// --- Anti-abuse: prove the requester belongs to the firm ---
// The requester's email domain must match the firm's listed contact-email domain
// (per-solicitor records carry `email`) or the firm's website host (`website`).
// No manual verification needed. Returns false on any malformed input.
export function emailDomain(email: string): string {
  if (!email) return "";
  const at = email.indexOf("@");
  if (at < 0) return "";
  return email.slice(at + 1).toLowerCase().trim();
}

export function emailDomainsMatch(a: string, b: string): boolean {
  const da = emailDomain(a);
  const db = emailDomain(b);
  return Boolean(da) && da === db;
}

export function emailDomainMatchesUrl(email: string, url: string | null | undefined): boolean {
  const ed = emailDomain(email);
  if (!ed || !url) return false;
  try {
    const host = new URL(/^https?:\/\//.test(url) ? url : `https://${url}`).hostname.toLowerCase().replace(/^www\./, "");
    return ed === host || ed.endsWith(`.${host}`) || host.endsWith(`.${ed}`);
  } catch {
    return false;
  }
}
