"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/** Re-mounts page content on navigation so it enters with a short fade and rise (CSS, reduced-motion aware). */
export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="page-enter">
      {children}
    </div>
  );
}
