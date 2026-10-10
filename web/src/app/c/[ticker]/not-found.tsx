import { NotFoundPanel } from "@/components/StatusPanels";

/** Catches notFound() from the [changeId] layout: the comparison exists, the change id does not. */
export default function ChangeNotFound() {
  return <NotFoundPanel kind="change" />;
}
