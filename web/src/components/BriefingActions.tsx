"use client";

import { useEffect, useRef, useState } from "react";

import { writeBriefingDraft } from "@/components/BriefingPicker";
import { DEFAULT_TITLE } from "@/lib/briefing/selection";

const PDF_UNAVAILABLE_MESSAGE = "PDF rendering is unavailable on this machine. Use Print and choose Save as PDF.";
const PRINT_FRAME_ID = "riskdiff-briefing-print-frame";

const primaryButton =
  "inline-flex h-10 cursor-pointer items-center rounded-md bg-accent px-4 text-sm font-medium text-on-accent hover:bg-accent-strong aria-disabled:cursor-wait aria-disabled:opacity-70";
const secondaryButton =
  "inline-flex h-10 cursor-pointer items-center rounded-md border border-line-input bg-surface px-4 text-sm font-medium text-ink hover:border-ink aria-disabled:cursor-wait aria-disabled:opacity-70";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** "riskdiff-briefing-NVDA.pdf" from Content-Disposition, else the fallback. Only a safe file name is kept. */
function filenameFrom(header: string | null, fallback: string): string {
  const m = header ? /filename="([A-Za-z0-9.\-]{1,120}\.pdf)"/.exec(header) : null;
  return m ? m[1] : fallback;
}

/**
 * The preview's actions: Download PDF (fetch + blob with JS, the plain link without), Print (loads
 * the bare print route in a hidden frame and opens the print dialog; the link opens it in a new tab
 * without JS) and Copy link. Messages go to one polite live region. The current selection is saved
 * so "Edit selection" opens the picker prefilled.
 */
export function BriefingActions({
  pdfHref,
  printHref,
  fallbackFilename,
  tickers,
  title,
  preparedFor,
}: {
  pdfHref: string;
  printHref: string;
  fallbackFilename: string;
  tickers: string[];
  title: string;
  preparedFor: string | null;
}) {
  const [downloading, setDownloading] = useState(false);
  const [printing, setPrinting] = useState(false);
  const [message, setMessage] = useState<{ text: string; tone: "info" | "warn" } | null>(null);
  const clearTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const tickerKey = tickers.join(",");
  useEffect(() => {
    writeBriefingDraft({ tickers: tickerKey.split(","), title: title === DEFAULT_TITLE ? "" : title, preparedFor: preparedFor ?? "" });
  }, [tickerKey, title, preparedFor]);

  useEffect(
    () => () => {
      if (clearTimer.current) clearTimeout(clearTimer.current);
      document.getElementById(PRINT_FRAME_ID)?.remove();
    },
    [],
  );

  function say(text: string, tone: "info" | "warn" = "info", clearAfterMs?: number) {
    if (clearTimer.current) clearTimeout(clearTimer.current);
    setMessage({ text, tone });
    if (clearAfterMs) clearTimer.current = setTimeout(() => setMessage(null), clearAfterMs);
  }

  async function onDownload(e: React.MouseEvent<HTMLAnchorElement>) {
    e.preventDefault();
    if (downloading) return;
    setDownloading(true);
    say("Preparing the PDF. This takes a few seconds.");
    try {
      const res = await fetch(pdfHref, { cache: "no-store" });
      const type = res.headers.get("content-type") ?? "";
      if (!res.ok || !type.startsWith("application/pdf")) throw new Error(`status ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filenameFrom(res.headers.get("content-disposition"), fallbackFilename);
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
      say("PDF downloaded.", "info", 4000);
    } catch {
      say(PDF_UNAVAILABLE_MESSAGE, "warn");
    } finally {
      setDownloading(false);
    }
  }

  function onPrint(e: React.MouseEvent<HTMLAnchorElement>) {
    e.preventDefault();
    if (printing) return;
    setPrinting(true);
    document.getElementById(PRINT_FRAME_ID)?.remove();
    const frame = document.createElement("iframe");
    frame.id = PRINT_FRAME_ID;
    frame.title = "Briefing print layout";
    frame.tabIndex = -1;
    frame.setAttribute("aria-hidden", "true");
    // Off screen but laid out at desktop width, so the print layout matches the PDF.
    frame.style.cssText = "position:fixed;left:-10000px;top:0;width:1280px;height:1024px;border:0;";
    const openInTab = () => window.open(printHref, "_blank", "noopener");
    frame.addEventListener(
      "load",
      async () => {
        try {
          const doc = frame.contentDocument;
          const win = frame.contentWindow;
          if (!doc || !win) throw new Error("no frame document");
          for (let i = 0; i < 150 && !doc.querySelector('[data-briefing-ready="1"]'); i++) await sleep(100);
          if (!doc.querySelector('[data-briefing-ready="1"]')) throw new Error("print layout not ready");
          // Paper is light: print the light theme whatever the screen uses.
          doc.documentElement.setAttribute("data-theme", "light");
          await doc.fonts.ready;
          win.focus();
          win.print();
        } catch {
          openInTab();
        } finally {
          setPrinting(false);
        }
      },
      { once: true },
    );
    frame.src = printHref;
    document.body.appendChild(frame);
  }

  async function onCopy() {
    const href = window.location.href;
    let ok = false;
    try {
      await navigator.clipboard.writeText(href);
      ok = true;
    } catch {
      // Clipboard API unavailable (insecure origin, permissions): legacy copy from a hidden field.
      try {
        const field = document.createElement("textarea");
        field.value = href;
        field.setAttribute("readonly", "");
        field.style.cssText = "position:fixed;left:-10000px;top:0;";
        document.body.appendChild(field);
        field.select();
        ok = document.execCommand("copy");
        field.remove();
      } catch {
        ok = false;
      }
    }
    say(ok ? "Copied" : "Could not copy. Copy the address from the address bar.", ok ? "info" : "warn", ok ? 2500 : undefined);
  }

  return (
    <div className="flex flex-col items-end gap-1.5">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <a href={pdfHref} download={fallbackFilename} onClick={onDownload} aria-disabled={downloading || undefined} className={primaryButton}>
          {downloading ? "Preparing PDF…" : "Download PDF"}
        </a>
        <a href={printHref} target="_blank" rel="noopener" onClick={onPrint} aria-disabled={printing || undefined} className={secondaryButton}>
          {printing ? "Preparing…" : "Print"}
        </a>
        <button type="button" onClick={onCopy} className={secondaryButton}>
          Copy link
        </button>
      </div>
      <p role="status" aria-live="polite" className={`min-h-[1.5em] text-sm ${message?.tone === "warn" ? "font-medium text-ink" : "text-ink-secondary"}`}>
        {message?.text ?? ""}
      </p>
    </div>
  );
}
