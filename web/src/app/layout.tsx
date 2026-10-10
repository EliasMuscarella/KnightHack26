import type { Metadata } from "next";
import { Public_Sans, Source_Serif_4 } from "next/font/google";
import Link from "next/link";

import { HeaderSearch } from "@/components/HeaderSearch";
import { LibraryStatusLine } from "@/components/LibraryStatus";
import { DISCLAIMER } from "@/lib/copy";
import { getLibraryStatus } from "@/lib/data";
import "./globals.css";

// DESIGN.md: Public Sans for the interface, Source Serif 4 for the filing's own words.
const publicSans = Public_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-public-sans",
  display: "swap",
});
const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
  variable: "--font-source-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "RiskDiff: what changed in a company's risk disclosures",
    template: "%s · RiskDiff",
  },
  description:
    "RiskDiff compares the risk factors in a company's last two annual reports (10-K) and shows exactly what management added, removed, or changed, with every quote linked to the SEC filing.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const libraryStatus = await getLibraryStatus();
  return (
    <html lang="en" className={`h-full ${publicSans.variable} ${sourceSerif.variable}`}>
      <body className="flex min-h-full flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <header className="sticky top-0 z-40 border-b border-line bg-surface">
          <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-8 px-8">
            <Link href="/" className="flex items-baseline gap-1.5 text-lg font-bold tracking-tight text-ink">
              <span aria-hidden="true" className="font-mono text-base text-add-fg">
                +
              </span>
              <span>RiskDiff</span>
              <span aria-hidden="true" className="font-mono text-base text-del-fg">
                −
              </span>
            </Link>
            <nav aria-label="Main" className="flex items-center gap-5 text-sm font-medium">
              <Link href="/" className="text-ink-muted hover:text-ink hover:underline">
                Home
              </Link>
              <Link href="/methodology" className="text-ink-muted hover:text-ink hover:underline">
                Methodology
              </Link>
              <Link href="/trends" className="text-ink-muted hover:text-ink hover:underline">
                Trends
              </Link>
            </nav>
            <HeaderSearch />
          </div>
        </header>
        <main id="main" className="flex-1">
          {children}
        </main>
        <footer className="mt-16 border-t border-line bg-surface">
          <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-4 px-8 py-6 text-sm">
            <p className="font-medium text-ink">
              <span aria-hidden="true">ⓘ </span>
              {DISCLAIMER}
            </p>
            <div className="space-y-0.5">
              <p className="text-ink-faint">
                Source text: the Risk Factors section of SEC EDGAR 10-K filings.{" "}
                <Link href="/methodology" className="underline hover:text-ink">
                  How RiskDiff works
                </Link>
              </p>
              <LibraryStatusLine status={libraryStatus} />
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
