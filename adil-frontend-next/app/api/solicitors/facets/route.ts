import { proxyToBackend } from "@/lib/proxy";

// Filter-facets proxy → adil-rag-api GET /api/v1/solicitors/facets.
// Returns { areas, area_groups: [{ group, wave, count }], languages } which
// drive the finder's filter UI. Wave-3 gating is applied client-side.
export async function GET(request: Request) {
  const upstream = await proxyToBackend(request, `/api/v1/solicitors/facets`, {
    method: "GET",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
