import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { randomUUID } from "crypto";
import type { ContentType } from "./types";

function envOrThrow(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`${name} is not configured`);
  return v;
}

let _client: S3Client | null = null;

export function getR2Client(): S3Client {
  if (_client) return _client;
  _client = new S3Client({
    region: "auto",
    endpoint: envOrThrow("R2_ENDPOINT"),
    credentials: {
      accessKeyId: envOrThrow("R2_FRONTEND_ACCESS_KEY_ID"),
      secretAccessKey: envOrThrow("R2_FRONTEND_SECRET_ACCESS_KEY"),
    },
    forcePathStyle: false,
  });
  return _client;
}

export function getR2Bucket(): string {
  return envOrThrow("R2_BUCKET");
}

export interface PresignResult {
  uploadId: string;
  objectKey: string;
  presignedUrl: string;
  expiresAt: string;
}

const EXT: Record<ContentType, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/webp": "webp",
};

export async function presignUpload(args: {
  conversationId: string;
  contentType: ContentType;
  sizeBytes: number;
  expirySeconds?: number;
}): Promise<PresignResult> {
  const client = getR2Client();
  const bucket = getR2Bucket();
  const uploadId = randomUUID();
  const ext = EXT[args.contentType];
  const objectKey = `uploads/${args.conversationId}/${uploadId}.${ext}`;

  const command = new PutObjectCommand({
    Bucket: bucket,
    Key: objectKey,
    ContentType: args.contentType,
    ContentLength: args.sizeBytes,
  });

  const expirySeconds = args.expirySeconds ?? 300;
  const presignedUrl = await getSignedUrl(client, command, { expiresIn: expirySeconds });
  const expiresAt = new Date(Date.now() + expirySeconds * 1000).toISOString();

  return { uploadId, objectKey, presignedUrl, expiresAt };
}
