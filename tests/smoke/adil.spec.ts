/**
 * UI smoke for adil (askadil.org) — runs every 15 min on this project's CI.
 *
 * Verifies the full user-facing pipeline:
 *   1. Frontend renders (Cloudflare + Next.js + Vercel-style serve OK)
 *   2. Jurisdiction picker present
 *   3. Selecting jurisdiction enables the chat input
 *   4. Real query reaches rag-api and Claude Sonnet streams a substantive
 *      response (catches FST 403, OpenAI/Anthropic outages, empty-corpus,
 *      rate limits, frontend wiring drift).
 *
 * Failure -> Telegram DM in the adil bot's chat AND MSentry /feedback.
 * The two reports are independent — clearing MSENTRY_FEEDBACK_* offboards.
 */
import { test, expect } from '@playwright/test';

const SITE_URL = process.env.SMOKE_URL ?? 'https://askadil.org';
const PROJECT = 'adil';
// Phrases that appear ONLY in real legal answers, not the page placeholder.
// At least one must be present in the streamed Claude response.
const ANSWER_PATTERN = /Equality Act 2010|Section 13|protected characteristic/i;

async function notify(
  severity: 'info' | 'warn' | 'error' | 'critical',
  message: string,
  context: Record<string, any> = {},
) {
  const tasks: Promise<unknown>[] = [];

  // 1) Project-local Telegram chat (always)
  const tgToken = process.env.TELEGRAM_BOT_TOKEN;
  const tgChatId = process.env.TELEGRAM_CHAT_ID;
  if (tgToken && tgChatId) {
    const emoji = { info: 'ℹ️', warn: '⚠️', error: '❌', critical: '🟥' }[severity];
    const text = `${emoji} *${severity.toUpperCase()}* \`ui_smoke\`\n${message}`;
    tasks.push(
      fetch(`https://api.telegram.org/bot${tgToken}/sendMessage`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          chat_id: tgChatId,
          text,
          parse_mode: 'Markdown',
          disable_web_page_preview: true,
        }),
      }).catch(() => {
        /* never fail the test on notify failure */
      }),
    );
  }

  // 2) MSentry central inbox (optional — silent no-op if env unset)
  const msUrl = process.env.MSENTRY_FEEDBACK_URL;
  const msSecret = process.env.MSENTRY_FEEDBACK_SECRET;
  if (msUrl && msSecret) {
    tasks.push(
      fetch(msUrl, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          secret: msSecret,
          project: process.env.MSENTRY_PROJECT ?? PROJECT,
          severity,
          kind: 'ui_smoke',
          message,
          context,
        }),
      }).catch(() => {}),
    );
  }

  await Promise.allSettled(tasks);
}

test.describe('@adil UI smoke', () => {
  test.setTimeout(60_000);

  test('golden path: load, pick jurisdiction, query, get substantive answer', async ({
    page,
  }, testInfo) => {
    let step = 'navigate';
    try {
      // 1. Page renders
      step = 'goto';
      await page.goto(SITE_URL, { waitUntil: 'domcontentloaded' });
      await expect(page).toHaveTitle(/AskAdil/);

      // 2. Jurisdiction picker is visible and clickable
      step = 'jurisdiction-visible';
      const ewButton = page.getByRole('button', { name: /England & Wales/ });
      await expect(ewButton).toBeVisible({ timeout: 10_000 });

      step = 'jurisdiction-click';
      await ewButton.click();

      // 3. Chat input becomes enabled
      step = 'input-enabled';
      const input = page.getByRole('textbox', {
        name: /Ask about discrimination/i,
      });
      await expect(input).toBeEnabled({ timeout: 5_000 });

      // 4. Submit a real legal query and wait for a substantive streamed reply
      step = 'submit-query';
      await input.fill('What is direct discrimination under the Equality Act 2010?');
      await input.press('Enter');

      // 5. The user message ("You ask...") should render quickly — confirms submit went through
      step = 'user-message-rendered';
      await expect(page.getByText(/You ask/i).first()).toBeVisible({ timeout: 5_000 });

      // 6. Streamed answer should arrive within 30s mentioning real legal content.
      //    ANSWER_PATTERN is chosen to NOT match the page placeholder text.
      step = 'wait-for-answer';
      await expect(page.getByText(ANSWER_PATTERN).first()).toBeVisible({
        timeout: 30_000,
      });

      // 7. No error event surfaced (catches PERMISSION_DENIED / 500s / empty answers)
      step = 'check-no-error';
      const errorBanner = page.getByText(/internal error|PERMISSION_DENIED|⚠️|I apologise/i);
      await expect(errorBanner).toHaveCount(0);

      await notify('info', 'ui_smoke OK — golden path passed', {
        url: SITE_URL,
        ci_run: process.env.GITHUB_RUN_ID ?? 'local',
      });
    } catch (err) {
      const screenshotPath = testInfo.outputPath('failure.png');
      await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
      await notify(
        'critical',
        `UI smoke FAILED at step \`${step}\`: ${(err as Error).message}`,
        {
          url: SITE_URL,
          step,
          ci_run: process.env.GITHUB_RUN_ID ?? 'local',
        },
      );
      throw err;
    }
  });
});
