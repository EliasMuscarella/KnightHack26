"use client";

import { useEffect, useSyncExternalStore } from "react";

/**
 * Light / dark / system theme switch. One small icon button that cycles
 * system -> light -> dark -> system. The choice lives in localStorage under THEME_KEY
 * ("system" is stored as no key). The inline script in layout.tsx applies the same rule
 * before first paint, so there is no flash of the wrong theme.
 */

type Choice = "system" | "light" | "dark";

export const THEME_KEY = "riskdiff-theme";
const CHANGE_EVENT = "riskdiff-theme-change";
const ORDER: Choice[] = ["system", "light", "dark"];

function readChoice(): Choice {
  try {
    const v = window.localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function writeChoice(choice: Choice): boolean {
  try {
    if (choice === "system") window.localStorage.removeItem(THEME_KEY);
    else window.localStorage.setItem(THEME_KEY, choice);
    return true;
  } catch {
    // Storage blocked (private mode, disabled site data): the choice lasts for this page only.
    return false;
  }
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme(choice: Choice) {
  const dark = choice === "dark" || (choice === "system" && systemPrefersDark());
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
}

// Holds the choice only when localStorage is blocked, for the life of the page.
let memoryChoice: Choice | null = null;

function subscribe(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

const getSnapshot = (): Choice => memoryChoice ?? readChoice();
const getServerSnapshot = (): Choice => "system";

const NEXT_LABEL: Record<Choice, string> = {
  system: "Theme: matches your system. Switch to light",
  light: "Theme: light. Switch to dark",
  dark: "Theme: dark. Switch to match your system",
};

export function ThemeToggle() {
  const choice = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  // Keep the page in step with the choice, and follow the OS while on "system".
  useEffect(() => {
    applyTheme(choice);
    if (choice !== "system" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystemChange = () => applyTheme("system");
    mq.addEventListener("change", onSystemChange);
    return () => mq.removeEventListener("change", onSystemChange);
  }, [choice]);

  const cycle = () => {
    const next = ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length];
    memoryChoice = writeChoice(next) ? null : next;
    window.dispatchEvent(new Event(CHANGE_EVENT));
  };

  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={NEXT_LABEL[choice]}
      title={NEXT_LABEL[choice]}
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-line text-ink-secondary hover:border-ink hover:text-ink"
    >
      <ThemeIcon choice={choice} />
    </button>
  );
}

function ThemeIcon({ choice }: { choice: Choice }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 20 20",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    focusable: false,
  };
  if (choice === "light") {
    return (
      <svg {...common}>
        <circle cx="10" cy="10" r="3.5" />
        <path d="M10 2.5v1.5M10 16v1.5M2.5 10H4M16 10h1.5M4.7 4.7l1.06 1.06M14.24 14.24l1.06 1.06M4.7 15.3l1.06-1.06M14.24 5.76l1.06-1.06" />
      </svg>
    );
  }
  if (choice === "dark") {
    return (
      <svg {...common}>
        <path d="M16.5 12.2A6.5 6.5 0 0 1 7.8 3.5a6.5 6.5 0 1 0 8.7 8.7Z" />
      </svg>
    );
  }
  // System: a circle half filled, light on one side and dark on the other.
  return (
    <svg {...common}>
      <circle cx="10" cy="10" r="6.5" />
      <path d="M10 3.5a6.5 6.5 0 0 1 0 13Z" fill="currentColor" stroke="none" />
    </svg>
  );
}
