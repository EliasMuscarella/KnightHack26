"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  ["/", "Home"],
  ["/trends", "Trends"],
  ["/briefing", "Briefing"],
  ["/methodology", "Methodology"],
] as const;

/** Main navigation with a sliding underline on the current section. */
export function NavLinks() {
  const pathname = usePathname() ?? "/";
  return (
    <nav aria-label="Main" className="flex items-center gap-6 text-sm">
      {NAV.map(([href, label]) => {
        const current = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link key={href} href={href} aria-current={current ? "page" : undefined} className={`nav-link ${current ? "text-ink" : "text-ink-secondary hover:text-ink"}`}>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
