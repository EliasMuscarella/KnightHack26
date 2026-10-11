"use client";

import { useEffect } from "react";

/**
 * Marks <html> as the bare print route so briefing.css hides the site header, footer and page
 * padding. (briefing.css also hides them with a :has() rule, so the first paint is already bare.)
 */
export function BriefingPrintMode() {
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add("briefing-print");
    return () => root.classList.remove("briefing-print");
  }, []);
  return null;
}
