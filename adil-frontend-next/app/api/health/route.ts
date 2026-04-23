import { NextResponse } from "next/server";

export async function GET() {
  // Always return 200 for Railway healthcheck — frontend is healthy if it can respond
  return NextResponse.json({ status: "ok" });
}
