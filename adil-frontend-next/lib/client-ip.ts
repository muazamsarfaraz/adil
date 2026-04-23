export function extractClientIp(request: Request): string {
  const cf = request.headers.get("cf-connecting-ip");
  if (cf && cf.trim()) return cf.trim();

  const xff = request.headers.get("x-forwarded-for");
  if (xff && xff.trim()) {
    const parts = xff.split(",").map((s) => s.trim()).filter(Boolean);
    if (parts.length > 0) return parts[parts.length - 1];
  }

  const xri = request.headers.get("x-real-ip");
  if (xri && xri.trim()) return xri.trim();

  return "unknown";
}
