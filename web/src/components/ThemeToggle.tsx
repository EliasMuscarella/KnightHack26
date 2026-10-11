"use client";

import { useEffect, useSyncExternalStore } from "react";

/**
 * Light / dark theme switch. One small icon button that flips the theme on screen: every click
 * stores the opposite of what is shown now, so each click visibly changes the page. Until the
 * first click nothing is stored and the page follows the OS, live. The choice lives in
 * localStorage under THEME_KEY ("light" | "dark"; no key = follow the OS). The inline script in
 * layout.tsx applies the same rule before first paint, so there is no flash of the wrong theme.
 */

type Choice = "system" | "light" | "dark";
type Resolved = "light" | "dark";

export const THEME_KEY = "riskdiff-theme";
const CHANGE_EVENT = "riskdiff-theme-change";

function readChoice(): Choice {
  try {
    const v = window.localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function writeChoice(choice: Resolved): boolean {
  try {
    window.localStorage.setItem(THEME_KEY, choice);
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

// The stored choice: changes on a click here or in another tab.
function subscribeChoice(onChange: () => void) {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

const getChoice = (): Choice => memoryChoice ?? readChoice();
const getServerChoice = (): Choice => "system";

// The theme on screen: data-theme on <html>, set before paint by layout.tsx and after by applyTheme.
function subscribeResolved(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

const getResolved = (): Resolved =>
  document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
// The server cannot know the theme; null renders a neutral label until hydration reads the page.
const getServerResolved = (): Resolved | null => null;

const LABEL: Record<Resolved, string> = {
  light: "Theme: light. Switch to dark",
  dark: "Theme: dark. Switch to light",
};

export function ThemeToggle() {
  const choice = useSyncExternalStore(subscribeChoice, getChoice, getServerChoice);
  const resolved = useSyncExternalStore(subscribeResolved, getResolved, getServerResolved);

  // Keep the page in step with the choice. Reads the live store, not `choice`: the hydration pass
  // renders with the server snapshot ("system"), and applying that would flash the OS theme.
  useEffect(() => {
    applyTheme(getChoice());
  }, [choice]);

  // Follow the OS live, but only while nothing is stored.
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystemChange = () => {
      if (getChoice() === "system") applyTheme("system");
    };
    mq.addEventListener("change", onSystemChange);
    return () => mq.removeEventListener("change", onSystemChange);
  }, []);

  const flip = () => {
    const next: Resolved = getResolved() === "dark" ? "light" : "dark";
    memoryChoice = writeChoice(next) ? null : next;
    window.dispatchEvent(new Event(CHANGE_EVENT));
  };

  const label = resolved ? LABEL[resolved] : "Switch between light and dark theme";

  return (
    <button
      type="button"
      onClick={flip}
      aria-label={label}
      title={label}
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-line text-ink-secondary hover:border-ink hover:text-ink"
    >
      <ThemeIcon />
    </button>
  );
}

// Both icons are rendered and CSS picks one from data-theme, so the server HTML already shows the
// right icon at first paint: a sun on the light theme, a moon on the dark one.
function ThemeIcon() {
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
  return (
    <>
      <svg {...common} className="dark:hidden" data-icon="sun">
        <circle cx="10" cy="10" r="3.5" />
        <path d="M10 2.5v1.5M10 16v1.5M2.5 10H4M16 10h1.5M4.7 4.7l1.06 1.06M14.24 14.24l1.06 1.06M4.7 15.3l1.06-1.06M14.24 5.76l1.06-1.06" />
      </svg>
      <svg {...common} className="hidden dark:block" data-icon="moon">
        <path d="M16.5 12.2A6.5 6.5 0 0 1 7.8 3.5a6.5 6.5 0 1 0 8.7 8.7Z" />
      </svg>
    </>
  );
}
