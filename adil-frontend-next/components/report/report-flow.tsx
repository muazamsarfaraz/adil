"use client";

import { useState } from "react";
import ReportTargetPicker from "./report-target-picker";
import ReportModal from "./report-modal";

export interface ReportState {
  targetId: string;
  name: string;
  email: string;
  phone?: string;
  dob?: string;
  address?: string;
  summary: string;
  date?: string;
  location?: string;
}

type Step = "pick_target" | "collect_details" | "review";

const inputStyle: React.CSSProperties = {
  width: "100%",
  marginTop: 6,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid rgba(15,62,41,0.20)",
  background: "var(--color-paper)",
  color: "var(--color-ink)",
  fontFamily: "var(--font-body)",
  fontSize: 14,
  outline: "none",
};

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="font-ui text-[10px] uppercase"
      style={{ letterSpacing: "0.22em", color: "var(--color-emerald)" }}
    >
      {children}
    </span>
  );
}

export default function ReportFlow({ onComplete }: { onComplete: (reference: string) => void }) {
  const [step, setStep] = useState<Step>("pick_target");
  const [state, setState] = useState<ReportState>({
    targetId: "",
    name: "",
    email: "",
    summary: "",
  });

  if (step === "pick_target") {
    return (
      <div className="paper-card p-6 my-6 max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-4">
          <span
            className="font-ui text-[11px] uppercase"
            style={{ letterSpacing: "0.24em", color: "var(--color-gold)" }}
          >
            ❃ Submit a report
          </span>
          <div
            className="flex-1 h-px"
            style={{
              background: "linear-gradient(to right, var(--color-gold) 0%, transparent 70%)",
              opacity: 0.5,
            }}
          />
        </div>
        <p
          className="font-body mb-1"
          style={{ fontSize: 15, lineHeight: 1.6, color: "var(--color-ink-soft)" }}
        >
          Where would you like to submit your report?
        </p>
        <ReportTargetPicker
          onSelect={(id) => {
            setState({ ...state, targetId: id });
            setStep("collect_details");
          }}
        />
      </div>
    );
  }

  if (step === "collect_details") {
    const canContinue = state.name && state.email && state.summary.length >= 10;
    return (
      <div className="paper-card p-6 md:p-7 my-6 max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-4">
          <span
            className="font-ui text-[11px] uppercase"
            style={{ letterSpacing: "0.24em", color: "var(--color-gold)" }}
          >
            ❃ Incident details
          </span>
          <div
            className="flex-1 h-px"
            style={{
              background: "linear-gradient(to right, var(--color-gold) 0%, transparent 70%)",
              opacity: 0.5,
            }}
          />
        </div>
        <p
          className="font-body italic mb-5"
          style={{ fontSize: 13, color: "var(--color-ink-faded)" }}
        >
          Kept private — never sent to the AI assistant.
        </p>

        <div className="space-y-4">
          <label className="block">
            <FieldLabel>Name</FieldLabel>
            <input
              style={inputStyle}
              value={state.name}
              onChange={(e) => setState({ ...state, name: e.target.value })}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--color-gold)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "rgba(15,62,41,0.20)")}
            />
          </label>
          <label className="block">
            <FieldLabel>Email</FieldLabel>
            <input
              type="email"
              style={inputStyle}
              value={state.email}
              onChange={(e) => setState({ ...state, email: e.target.value })}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--color-gold)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "rgba(15,62,41,0.20)")}
            />
          </label>
          <label className="block">
            <FieldLabel>What happened?</FieldLabel>
            <textarea
              style={{ ...inputStyle, resize: "vertical", lineHeight: 1.6 }}
              rows={5}
              value={state.summary}
              onChange={(e) => setState({ ...state, summary: e.target.value })}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--color-gold)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "rgba(15,62,41,0.20)")}
            />
          </label>
          <label className="block">
            <FieldLabel>Date (optional)</FieldLabel>
            <input
              type="date"
              style={inputStyle}
              value={state.date ?? ""}
              onChange={(e) => setState({ ...state, date: e.target.value })}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--color-gold)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "rgba(15,62,41,0.20)")}
            />
          </label>
        </div>

        <div className="flex justify-end mt-6">
          <button
            disabled={!canContinue}
            onClick={() => setStep("review")}
            className="font-ui transition-all"
            style={{
              padding: "10px 22px",
              borderRadius: 999,
              fontSize: 13,
              letterSpacing: "0.04em",
              fontWeight: 500,
              background: canContinue ? "var(--color-ink)" : "rgba(15,62,41,0.2)",
              color: canContinue ? "var(--color-paper)" : "rgba(244,238,220,0.6)",
              border: `1px solid ${canContinue ? "var(--color-ink)" : "rgba(15,62,41,0.2)"}`,
              cursor: canContinue ? "pointer" : "not-allowed",
            }}
            onMouseEnter={(e) => {
              if (canContinue) {
                e.currentTarget.style.background = "var(--color-emerald)";
                e.currentTarget.style.borderColor = "var(--color-emerald)";
              }
            }}
            onMouseLeave={(e) => {
              if (canContinue) {
                e.currentTarget.style.background = "var(--color-ink)";
                e.currentTarget.style.borderColor = "var(--color-ink)";
              }
            }}
          >
            Review &amp; submit →
          </button>
        </div>
      </div>
    );
  }

  return (
    <ReportModal
      state={state}
      onCancel={() => setStep("collect_details")}
      onSubmitted={(ref) => {
        setStep("pick_target");
        onComplete(ref);
      }}
    />
  );
}
