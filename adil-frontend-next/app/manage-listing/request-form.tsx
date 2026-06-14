"use client";

import { useState } from "react";

const INPUT =
  "w-full font-body bg-[color:var(--color-paper)] border border-[color:var(--color-ink)]/25 rounded-lg px-3 py-2 text-[color:var(--color-ink)]";
const LABEL =
  "font-ui text-[12px] uppercase text-[color:var(--color-ink-faded)] block mb-1.5";

export default function RequestLinkForm({ error }: { error?: string }) {
  const [sraId, setSraId] = useState("");
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("sending");
    try {
      const r = await fetch("/api/listing/request-link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sra_id: sraId.trim(), email: email.trim() }),
      });
      setState(r.ok ? "sent" : "error");
    } catch {
      setState("error");
    }
  }

  if (state === "sent") {
    return (
      <div className="paper-card p-6">
        <p className="font-body text-[color:var(--color-ink-soft)]">
          If <strong>{email}</strong> is the contact on record for SRA ID <strong>{sraId}</strong>, we've
          emailed a secure sign-in link. It's valid for 7 days — check your inbox.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="paper-card p-6 space-y-4">
      {error && (
        <p className="font-body text-[color:var(--color-rust)]" role="alert">
          That link was {error}. Request a new one below.
        </p>
      )}
      <p className="font-body text-[color:var(--color-ink-soft)]">
        Enter your SRA ID and the email on record for your firm. We'll email you a secure link to manage your
        listing.
      </p>
      <label className="block">
        <span className={LABEL}>SRA ID</span>
        <input
          className={INPUT}
          value={sraId}
          onChange={(e) => setSraId(e.target.value)}
          inputMode="numeric"
          autoComplete="off"
          required
        />
      </label>
      <label className="block">
        <span className={LABEL}>Work email</span>
        <input
          className={INPUT}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@yourfirm.co.uk"
          required
        />
      </label>
      <button type="submit" className="btn-primary" disabled={state === "sending"}>
        {state === "sending" ? "Sending…" : "Email me a sign-in link"}
      </button>
      {state === "error" && (
        <p className="font-body text-[color:var(--color-rust)]" role="alert">
          Something went wrong. Please try again.
        </p>
      )}
    </form>
  );
}
