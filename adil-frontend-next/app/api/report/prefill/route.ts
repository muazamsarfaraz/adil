import { proxyToBackend } from "@/lib/proxy";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (!body) return Response.json({ details: "", location: null, date_time: null });
  try {
    const upstream = await proxyToBackend(request, "/api/v1/report/prefill", { body });
    if (!upstream.ok) return Response.json({ details: "", location: null, date_time: null });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return Response.json({ details: "", location: null, date_time: null });
  }
}
