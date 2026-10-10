import { NotFoundPanel } from "@/components/StatusPanels";

/** Catches notFound() from the /c/[ticker] layout: no comparison for that ticker. */
export default function ComparisonNotFound() {
  return <NotFoundPanel kind="comparison" />;
}
