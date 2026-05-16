// Next.js instrumentation hook — runs once at server startup.
// Sends an MSentry deploy ping on cold start. No-ops if MSENTRY_* env unset.
// Docs: https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation

export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { notify } = require('./lib/msentry_notify');
    notify('info', 'deploy', 'adil-frontend-next started', { commit: process.env.RAILWAY_GIT_COMMIT_SHA || 'unknown' });
  }
}
