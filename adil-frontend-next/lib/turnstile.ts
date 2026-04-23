const VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

export interface TurnstileResult {
  success: boolean;
  errorCodes?: string[];
}

export async function verifyTurnstile(token: string, remoteIp?: string): Promise<TurnstileResult> {
  const secret = process.env.TURNSTILE_SECRET;
  if (!secret) throw new Error("TURNSTILE_SECRET is not configured");

  const body = new URLSearchParams();
  body.set("secret", secret);
  body.set("response", token);
  if (remoteIp && remoteIp !== "unknown") body.set("remoteip", remoteIp);

  const resp = await fetch(VERIFY_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
    signal: AbortSignal.timeout(5_000),
  });

  if (!resp.ok) return { success: false, errorCodes: [`http-${resp.status}`] };

  const data = (await resp.json()) as { success: boolean; "error-codes"?: string[] };
  return { success: data.success === true, errorCodes: data["error-codes"] };
}
