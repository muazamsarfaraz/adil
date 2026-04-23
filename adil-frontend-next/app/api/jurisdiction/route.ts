import { proxyToBackend } from "@/lib/proxy";

export async function GET(request: Request) {
  const upstream = await proxyToBackend(request, "/api/v1/detect-jurisdiction", { method: "GET" });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
