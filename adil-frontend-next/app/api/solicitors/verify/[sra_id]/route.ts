import { proxyToBackend } from "@/lib/proxy";

// SRA-ID verification proxy → adil-rag-api GET /api/v1/solicitors/verify/{sra_id}.
// Returns { solicitor, disclaimer } when the ID is present in the bundled
// LegalScraper directory, or 404 when it is not. The page uses this to let a
// user paste an SRA number and confirm it against AskAdil's directory.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ sra_id: string }> },
) {
  const { sra_id } = await params;
  const upstream = await proxyToBackend(
    request,
    `/api/v1/solicitors/verify/${encodeURIComponent(sra_id)}`,
    { method: "GET" },
  );
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
