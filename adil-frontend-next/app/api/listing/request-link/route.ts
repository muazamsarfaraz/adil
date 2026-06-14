import { NextResponse } from "next/server";
import { mintEditToken, emailDomainsMatch, emailDomainMatchesUrl, publicOrigin } from "@/lib/edit-links";
import { getRagApiBaseUrl, getRagApiKey } from "@/lib/proxy";
import { sendEmail } from "@/lib/mailer";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// POST { sra_id, email } → mints a 7-day magic link and (when the email
// plausibly belongs to the firm) emails it. Always returns { ok: true } so the
// endpoint can't be used to enumerate which firms/emails are on record.
export async function POST(req: Request) {
  let body: { sra_id?: unknown; email?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Bad request." }, { status: 400 });
  }

  const sraId = String(body?.sra_id ?? "").trim();
  const email = String(body?.email ?? "").trim().toLowerCase();
  if (!sraId || !EMAIL_RE.test(email)) {
    return NextResponse.json({ ok: false, error: "Provide your SRA ID and a valid email." }, { status: 400 });
  }

  // Look up the record to (a) confirm it exists and (b) check affiliation.
  let record: { email?: string; website?: string } | null = null;
  try {
    const resp = await fetch(`${getRagApiBaseUrl()}/api/v1/solicitors/verify/${encodeURIComponent(sraId)}`, {
      headers: { "X-API-Key": getRagApiKey() },
      cache: "no-store",
    });
    if (resp.ok) record = (await resp.json())?.solicitor ?? null;
  } catch {
    // backend unavailable — fall through, just don't send
  }

  const affiliated =
    (record?.email && emailDomainsMatch(email, record.email)) ||
    (record?.website && emailDomainMatchesUrl(email, record.website));

  if (record && affiliated) {
    const token = mintEditToken(sraId, email);
    const origin = publicOrigin(req);
    const link = `${origin}/api/listing/verify?token=${encodeURIComponent(token)}`;
    const result = await sendEmail({
      to: email,
      subject: "Sign in to manage your AskAdil listing",
      text:
        `Assalamu alaikum,\n\n` +
        `Use this secure link to manage your AskAdil directory listing (SRA ID ${sraId}). ` +
        `It is valid for 7 days and is just for you:\n\n${link}\n\n` +
        `If you did not request this, you can ignore this email — nothing will change.\n\n` +
        `— AskAdil, a Muslim Council of Britain initiative`,
      html:
        `<p>Assalamu alaikum,</p>` +
        `<p>Use this secure link to manage your AskAdil directory listing (SRA ID <strong>${sraId}</strong>). ` +
        `It is valid for 7 days and is just for you:</p>` +
        `<p><a href="${link}">Manage my listing &rarr;</a></p>` +
        `<p style="color:#6b7668;font-size:13px">If you did not request this, you can ignore this email — nothing will change.</p>` +
        `<p style="color:#6b7668;font-size:13px">— AskAdil, a Muslim Council of Britain initiative</p>`,
    });
    if (!result.ok) {
      console.error(`[listing] magic-link email failed (mode=${result.mode}) for SRA ${sraId}`);
    }
  } else {
    console.log(`[listing] request-link: no affiliated match for SRA ${sraId} / ${email} — not sending`);
  }

  return NextResponse.json({ ok: true });
}
