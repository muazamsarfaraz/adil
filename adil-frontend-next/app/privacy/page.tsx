export const metadata = { title: "Privacy — AskAdil" };

export default function PrivacyPage() {
  return (
    <article className="prose max-w-3xl mx-auto py-10 px-4">
      <h1>Privacy notice</h1>
      <p><em>Last updated: April 2026.</em></p>
      <h2>What we collect</h2>
      <p>Anonymised conversation logs (no names, no contact details). IP address for rate limiting only.</p>
      <h2>What we do NOT collect</h2>
      <p>We do not collect user accounts. We do not track you across sites.</p>
      <h2>Hate crime reports</h2>
      <p>When you submit a hate crime report, your details are forwarded directly to the selected organisation
         (e.g. British Muslim Trust) and <strong>immediately discarded</strong> from our servers. We do not store your personal details.</p>
      <h2>AI processing</h2>
      <p>Chat messages are sent to Google Gemini under a zero-data-retention agreement.
         Google does not retain or train on your messages.</p>
      <h2>Contact</h2>
      <p>Email the MCB privacy team at privacy@mcb.org.uk.</p>
    </article>
  );
}
