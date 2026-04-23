import { PresignRequestSchema } from "@/lib/types";
import { presignUpload } from "@/lib/r2";
import { proxyToBackend } from "@/lib/proxy";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const parsed = PresignRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: "validation_failed", issues: parsed.error.issues }, { status: 400 });
  }

  const { conversation_id, content_type, size_bytes } = parsed.data;
  const { uploadId, objectKey, presignedUrl, expiresAt } = await presignUpload({
    conversationId: conversation_id,
    contentType: content_type,
    sizeBytes: size_bytes,
  });

  const record = await proxyToBackend(request, "/api/v1/uploads/record", {
    body: {
      id: uploadId,
      conversation_id,
      object_key: objectKey,
      content_type,
      size_bytes,
    },
  });
  if (record.status >= 300) {
    const detail = await record.text().catch(() => "");
    return Response.json({ error: "record_failed", detail }, { status: 502 });
  }

  return Response.json({
    upload_id: uploadId,
    object_key: objectKey,
    presigned_url: presignedUrl,
    expires_at: expiresAt,
  });
}
