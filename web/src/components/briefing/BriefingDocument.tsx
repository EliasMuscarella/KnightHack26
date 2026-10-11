/**
 * The Disclosure Briefing: a four-page, US Letter document for one or more companies, rendered from
 * a `BriefingModel` (lib/briefing/types.ts) and printed to PDF by the briefing PDF endpoint.
 *
 * Server component (no hooks). Styles and print rules: ./briefing.css (every selector under
 * `.briefing`; the paper stays light in both themes). Quotes are verbatim filing sentences drawn
 * with MarkedText (highlighter on inserts, strikes on deletes); nothing is paraphrased.
 *
 * Tree:
 *   BriefingDocument (article.briefing)
 *     SummaryPage      page 1: title, stat tiles, read these first, coverage table + change mix
 *     ThemesPage       page 2: theme quote cards, topic matrix (omitted when there are neither)
 *     EvidencePage     page 3: potential → actual, figures, new / dropped, quiet companies
 *     FollowUpsPage    page 4: questions, audit trail, method, fiscal-year note, notes
 *     disclaimer       screen only (the PDF endpoint prints it in the page footer)
 */
import type { BriefingModel } from "@/lib/briefing/types";

import { EvidencePage } from "./EvidencePage";
import { FollowUpsPage } from "./FollowUpsPage";
import { SummaryPage } from "./SummaryPage";
import { ThemesPage } from "./ThemesPage";

export const BRIEFING_DISCLAIMER =
  "RiskDiff measures changes in disclosed risk language, not changes in actual risk. Not investment advice.";

/** Notes about themes or topics follow the themes to page 1 when page 2 is omitted. */
const THEME_NOTE = /\b(theme|themes|topic|topics|matrix|keyword)\b/i;

export function BriefingDocument({ model }: { model: BriefingModel }) {
  const hasThemesPage = model.themes.length > 0 || model.matrix !== null;
  const movedNotes = hasThemesPage ? [] : model.notes.filter((n) => THEME_NOTE.test(n));
  const pageFourNotes = model.notes.filter((n) => !movedNotes.includes(n));
  // "Page 3." in read-these-first points at the evidence page, which becomes page 2 when the
  // themes page is omitted. (Spreading items, which point at page 2, only exist with themes.)
  const summaryModel: BriefingModel = hasThemesPage
    ? model
    : { ...model, readFirst: model.readFirst.map((i) => (i.pageRef === 3 ? { ...i, pageRef: 2 } : i)) };
  return (
    <article className="briefing" aria-label={model.title}>
      <SummaryPage model={summaryModel} movedNotes={movedNotes} />
      {hasThemesPage ? <ThemesPage model={model} /> : null}
      <EvidencePage model={model} />
      <FollowUpsPage model={model} notes={pageFourNotes} />
      <p className="bf-disclaimer">{BRIEFING_DISCLAIMER}</p>
    </article>
  );
}
