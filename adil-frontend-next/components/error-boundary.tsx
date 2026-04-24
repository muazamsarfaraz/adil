"use client";

import React from "react";

export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error: unknown) { console.error("ErrorBoundary caught", error); }
  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div
          className="p-4 font-body text-[14px] rounded-2xl"
          style={{
            background: "rgba(183, 74, 56, 0.08)",
            border: "1px solid rgba(183, 74, 56, 0.25)",
            color: "var(--color-rust)",
          }}
        >
          Something went wrong rendering this message. Please retry.
        </div>
      );
    }
    return this.props.children;
  }
}
