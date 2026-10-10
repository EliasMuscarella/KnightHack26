"use client";

/**
 * Error boundary for one page section: if drawing the section throws (an unexpected payload
 * item, say), the section is replaced by one quiet line and the rest of the page still renders.
 * Nothing about the error is shown to the reader.
 */
import { Component, type ReactNode } from "react";

interface Props {
  /** Short name of the section, for the console message only. */
  name: string;
  children: ReactNode;
}

interface State {
  failed: boolean;
}

export class SectionBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: unknown): void {
    // A warning, not an error: the page handled it. No stack traces or payloads in the UI.
    console.warn(`RiskDiff: the ${this.props.name} section could not be drawn.`, error instanceof Error ? error.message : String(error));
  }

  render(): ReactNode {
    if (this.state.failed) {
      return <p className="border-t border-line pt-4 text-base text-ink-secondary">This section could not be drawn.</p>;
    }
    return this.props.children;
  }
}
