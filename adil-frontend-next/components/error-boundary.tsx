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
        <div className="p-4 bg-red-50 text-red-800 rounded">
          Something went wrong rendering this message. Please retry.
        </div>
      );
    }
    return this.props.children;
  }
}
