import { proxyToBackend } from "@/lib/proxy";

// Per-solicitor search proxy → adil-rag-api GET /api/v1/solicitors/search.
// The backend filters by area / language / postcode / name / muslim_only and
// already applies suppressions server-side, so we just forward the query
// string verbatim. The API key is injected by proxyToBackend (server-side).
export async function GET(request: Request) {
  const qs = new URL(request.url).search;
  const upstream = await proxyToBackend(request, `/api/v1/solicitors/search${qs}`, {
    method: "GET",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
