import type { NextConfig } from "next";

// Build-time stamp surfaced in the UI so anyone can verify which deploy
// they're looking at. RAILWAY_GIT_COMMIT_SHA is injected automatically on
// every Railway deploy; we fall back to "dev" for local builds.
const buildSha = (process.env.RAILWAY_GIT_COMMIT_SHA ?? "dev").slice(0, 7);
const buildDate = new Date().toISOString().slice(0, 10);

const config: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_BUILD_SHA: buildSha,
    NEXT_PUBLIC_BUILD_DATE: buildDate,
  },
};

export default config;
