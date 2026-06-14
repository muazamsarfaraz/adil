import { NextResponse } from "next/server";
import { FIRM_COOKIE, publicOrigin } from "@/lib/edit-links";

// POST /api/listing/logout — clears the firm session cookie.
export async function POST(req: Request) {
  const origin = publicOrigin(req);
  const res = NextResponse.redirect(`${origin}/manage-listing`, { status: 303 });
  res.cookies.set({ name: FIRM_COOKIE, value: "", httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
