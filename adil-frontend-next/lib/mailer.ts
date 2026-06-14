// Outbound transactional email for adil-frontend-next.
//
// Ported from the sibling MCB project `mcb-ai-agm-ready-reckoner/lib/mailer.js`.
// HTTP-only senders (no SMTP dependency), chosen at call time by priority:
//   1. cloudflare — CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID
//                   (Cloudflare Email Sending REST API; requires askadil.com
//                    onboarded onto CF Email Sending). Token is minted by the
//                    `msentry-cf` `email-sender` role.
//   2. resend     — RESEND_API_KEY (HTTP fallback while CF onboarding settles)
//   3. console    — logs the body so the magic-link flow is testable from
//                   Railway logs with no mail provider configured.
//
// Server-only: import from route handlers only.

export interface SendArgs {
  to: string;
  subject: string;
  text?: string;
  html?: string;
}
export interface SendResult {
  ok: boolean;
  mode: "cloudflare" | "resend" | "console";
  id?: string;
  error?: unknown;
}

function mailFrom(): string {
  return process.env.MAIL_FROM ?? "AskAdil <no-reply@askadil.com>";
}
function mailReplyTo(): string {
  return process.env.MAIL_REPLY_TO ?? "info@mcb.org.uk";
}

// CF's REST API accepts `from` as a plain email string OR { address, name } —
// NOT RFC-822 "Name <email>". Parse MAIL_FROM either way.
function parseAddress(s: string): string | { address: string; name: string } {
  const m = /^\s*([^<]*?)\s*<\s*([^>]+?)\s*>\s*$/.exec(s);
  if (m) {
    const name = m[1].replace(/^"|"$/g, "").trim();
    const address = m[2].trim();
    return name ? { address, name } : address;
  }
  return s.trim();
}

export async function sendEmail(args: SendArgs): Promise<SendResult> {
  const cfToken = process.env.CLOUDFLARE_API_TOKEN;
  const cfAccount = process.env.CLOUDFLARE_ACCOUNT_ID;
  const resendKey = process.env.RESEND_API_KEY;

  if (cfToken && cfAccount) {
    const r = await sendCloudflare(args, cfToken, cfAccount);
    if (r.ok) return r;
    // CF failed (e.g. domain not yet onboarded) — try the HTTP fallback.
    if (resendKey) return sendResend(args, resendKey);
    return r;
  }
  if (resendKey) return sendResend(args, resendKey);
  return sendConsole(args);
}

async function sendCloudflare(args: SendArgs, token: string, account: string): Promise<SendResult> {
  try {
    const url = `https://api.cloudflare.com/client/v4/accounts/${account}/email/sending/send`;
    const body: Record<string, unknown> = {
      from: parseAddress(mailFrom()),
      to: args.to,
      subject: args.subject,
      reply_to: parseAddress(mailReplyTo()),
    };
    if (args.text) body.text = args.text;
    if (args.html) body.html = args.html;

    const res = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = (await res.json().catch(() => ({}))) as {
      success?: boolean;
      result?: { id?: string; delivered?: unknown[]; queued?: unknown[]; permanent_bounces?: unknown[] };
      id?: string;
    };
    if (!res.ok || data.success === false) {
      console.error(`[mailer:cloudflare] HTTP ${res.status}`, JSON.stringify(data).slice(0, 500));
      return { ok: false, mode: "cloudflare", error: data };
    }
    const r = data.result ?? {};
    const delivered = (r.delivered?.length ?? 0) + (r.queued?.length ?? 0);
    const bounced = r.permanent_bounces?.length ?? 0;
    if (delivered === 0 && bounced > 0) {
      return { ok: false, mode: "cloudflare", error: { permanent_bounces: r.permanent_bounces } };
    }
    return { ok: true, mode: "cloudflare", id: r.id ?? data.id };
  } catch (err) {
    console.error("[mailer:cloudflare] threw:", err);
    return { ok: false, mode: "cloudflare", error: String(err) };
  }
}

async function sendResend(args: SendArgs, key: string): Promise<SendResult> {
  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: mailFrom(),
        to: [args.to],
        subject: args.subject,
        text: args.text,
        html: args.html,
        reply_to: mailReplyTo(),
      }),
    });
    const data = (await res.json().catch(() => ({}))) as { id?: string };
    if (!res.ok) {
      console.error(`[mailer:resend] HTTP ${res.status}`, JSON.stringify(data).slice(0, 300));
      return { ok: false, mode: "resend", error: data };
    }
    return { ok: true, mode: "resend", id: data.id };
  } catch (err) {
    console.error("[mailer:resend] threw:", err);
    return { ok: false, mode: "resend", error: String(err) };
  }
}

function sendConsole(args: SendArgs): SendResult {
  console.log(`[mailer:console] to=${args.to} subject="${args.subject}"`);
  if (args.text) args.text.split("\n").forEach((l) => console.log(`[mailer:console] ${l}`));
  return { ok: true, mode: "console" };
}
