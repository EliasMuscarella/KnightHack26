import Link from "next/link";

/** The wordmark: plain type, with the product's one visual idea on the word that matters. */
export function Wordmark() {
  return (
    <Link href="/" className="text-base font-medium tracking-tight text-ink no-underline">
      Risk
      <span className="hl">Diff</span>
    </Link>
  );
}
