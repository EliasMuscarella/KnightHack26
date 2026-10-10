"use client";

import { ErrorPanel } from "@/components/StatusPanels";

export default function MethodologyError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return <ErrorPanel error={error} retry={retry} context="the methodology" />;
}
