"use client";

import { usePathname } from "next/navigation";

import { TickerSearch } from "@/components/TickerSearch";

/** Header ticker search. Hidden on the home page, which has its own large search box. */
export function HeaderSearch() {
  const pathname = usePathname();
  if (pathname === "/") return null;
  return (
    <div className="ml-auto w-[340px]">
      <TickerSearch size="compact" />
    </div>
  );
}
