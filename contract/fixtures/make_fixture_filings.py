"""Generate two synthetic 10-K-like HTML documents for end-to-end development.

They imitate the STRUCTURE of inline-XBRL 10-K filings (hidden ix:header, cover page, a table
of contents that repeats the Item 1A heading, page furniture, headings split across spans with
non-breaking spaces, bold risk headings, group headers) but every risk heading is prefixed with
"FIXTURE:" and the issuer is "FIXTURE Example Widgets Corp". Nothing here comes from a real filing.

Usage: uv run python contract/fixtures/make_fixture_filings.py
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
F = "FIXTURE: "

# (group header or None, heading, [body paragraphs])
OLD_RISKS = [
    ("Risks Related to Our Business and Industry", None, None),
    (
        None,
        F + "We depend on a limited number of third-party foundries to manufacture our widgets.",
        [
            "We do not own manufacturing facilities and rely on a small number of foundries located in Westland and Eastland. A disruption at any of these foundries could delay shipments and increase our costs. Natural disasters, political instability, or trade restrictions may affect our suppliers.",
            "We attempt to mitigate these risks by maintaining safety stock, but our efforts may not be sufficient. If we are unable to obtain adequate supplies of widgets on a timely basis, our revenue and gross margin could be adversely affected.",
        ],
    ),
    (
        None,
        F + "Security breaches could harm our business.",
        [
            "Our systems may be vulnerable to computer viruses, break-ins, and similar disruptions. A breach could result in the loss of confidential information and damage to our reputation. We may incur significant costs to remediate security incidents.",
        ],
    ),
    (
        None,
        F + "The widget market is intensely competitive.",
        [
            "We compete with larger companies that have greater resources, e.g. Megacorp and Omnicorp. If we fail to compete effectively, our market share and margins could decline. Our competitors may introduce products that are superior to ours or that are priced more aggressively, which could cause customers to delay or cancel orders.",
        ],
    ),
    (
        None,
        F + "We rely on a small number of customers for a significant portion of our revenue.",
        [
            "Sales to our ten largest customers accounted for approximately 55% of our revenue in fiscal 2024. The loss of any of these customers, or a significant reduction in their purchases, could materially reduce our revenue. Our customers generally are not obligated to purchase minimum quantities.",
        ],
    ),
    (
        None,
        F + "Our products may contain defects that could harm our reputation.",
        [
            "Our widgets are complex and may contain defects or errors, particularly when first introduced. Defects could result in product recalls, warranty claims, and loss of customer confidence. We maintain product liability insurance, but it may not be sufficient to cover all claims.",
        ],
    ),
    (
        None,
        F + "We may not be able to attract and retain qualified personnel.",
        [
            "Our success depends on the continued service of our senior management and engineering teams. Competition for qualified personnel in Widget City is intense. If we are unable to attract and retain employees, our product development efforts could be delayed. We rely on equity awards to compensate employees, and a decline in our stock price could reduce their retention value.",
        ],
    ),
    (
        None,
        F + "We may be unable to protect our intellectual property.",
        [
            "We rely on a combination of patents, trade secrets, and contractual provisions to protect our technology. Our patents may be challenged, invalidated, or circumvented. Third parties may assert that our products infringe their intellectual property rights, which could result in costly litigation or require us to obtain licenses on unfavorable terms.",
        ],
    ),
    (
        None,
        F + "Climate change and related regulation could affect our operations.",
        [
            "Extreme weather events could disrupt our facilities and those of our suppliers. New regulations relating to greenhouse gas emissions could increase our compliance costs. Customers may also require us to meet sustainability standards that increase our expenses.",
        ],
    ),
    ("Risks Related to Regulation and Legal Matters", None, None),
    (
        None,
        F
        + "The pending acquisition of Gadgetron Inc. may not be completed on the expected timeline.",
        [
            "Completion of the acquisition is subject to regulatory approvals in the U.S. and the E.U., which may be delayed or denied. If the acquisition is not completed, we may be required to pay a termination fee of $450 million. The announcement of the acquisition may also disrupt our relationships with customers and employees.",
        ],
    ),
    (
        None,
        F + "Changes in trade policy could increase our costs.",
        [
            "Tariffs on imported components could increase our cost of goods sold. We may be unable to pass these costs on to customers. Changes in export control regulations could also limit the markets in which we sell our products.",
        ],
    ),
    (
        None,
        F + "We are subject to environmental regulations that could increase our costs.",
        [
            "Our operations are subject to laws governing the use, storage, and disposal of hazardous materials. Compliance with these laws, including the Westland Clean Manufacturing Act, requires ongoing expenditures. Failure to comply could result in fines, suspension of production, or litigation.",
        ],
    ),
    ("Risks Related to Financial Matters", None, None),
    (
        None,
        F + "Fluctuations in foreign currency exchange rates could adversely affect our results.",
        [
            "Approximately 40% of our revenue is denominated in currencies other than the U.S. dollar. We use forward contracts to hedge a portion of this exposure, but hedging may not be effective. A strengthening U.S. dollar would reduce the reported value of our international revenue. We do not hedge translation exposure for our subsidiaries in Southland.",
        ],
    ),
    (
        None,
        F + "Our indebtedness could limit our flexibility.",
        [
            "As of January 28, 2024, we had $2.0 billion of senior notes outstanding. Our debt agreements contain covenants that restrict our ability to incur additional debt and pay dividends. If we fail to comply with these covenants, our lenders could accelerate repayment, which would harm our liquidity.",
        ],
    ),
    (
        None,
        F + "Changes in tax laws could affect our effective tax rate.",
        [
            "We are subject to income taxes in the U.S. and numerous foreign jurisdictions. Changes in tax laws, including the implementation of a global minimum tax, could increase our effective tax rate. Tax authorities may also challenge our transfer pricing arrangements, e.g. with respect to intercompany licensing.",
        ],
    ),
]

NEW_RISKS = [
    ("Risks Related to Our Business and Industry", None, None),
    (
        None,
        F + "We depend on a limited number of third-party foundries to manufacture our widgets.",
        [
            "We do not own manufacturing facilities and rely on a small number of foundries located in Westland, Eastland, and Ruritania. A disruption at any of these foundries could delay shipments and increase our costs. In fiscal 2025, export restrictions imposed by the Ruritanian government resulted in a shipment delay that reduced our revenue by approximately $1.2 billion. Natural disasters, political instability, or trade restrictions have affected and may continue to affect our suppliers.",
            "We attempt to mitigate these risks by maintaining safety stock, but our efforts may not be sufficient. If we are unable to obtain adequate supplies of widgets on a timely basis, our revenue and gross margin could be adversely affected. We are qualifying an additional foundry in Northland, which we expect to take at least 18 months.",
        ],
    ),
    (
        None,
        F
        + "Cybersecurity incidents, including ransomware, could materially disrupt our operations.",
        [
            "Our information technology systems and those of our vendors are vulnerable to ransomware, phishing, and state-sponsored attacks. An incident could result in the loss or exposure of confidential information, regulatory penalties, and damage to our reputation. We may incur significant costs to remediate security incidents, and our insurance may not cover all losses.",
        ],
    ),
    (
        None,
        F + "The widget market is intensely competitive.",
        [
            "We compete with larger companies that have greater resources, e.g. Megacorp and Omnicorp. If we fail to compete effectively, our market share and margins could decline. Our competitors may introduce products that are superior to ours or that are priced more aggressively, which could cause customers to delay or cancel orders.",
        ],
    ),
    (
        None,
        F + "We rely on a small number of customers for a significant portion of our revenue.",
        [
            "Sales to our ten largest customers accounted for approximately 61% of our revenue in fiscal 2025, and one customer, Megamart, accounted for 14%. The loss of any of these customers, or a significant reduction in their purchases, could materially reduce our revenue. Our customers generally are not obligated to purchase minimum quantities.",
        ],
    ),
    (
        None,
        F + "Our products may contain defects that could harm our reputation.",
        [
            "Our widgets are complex and may contain defects or errors, particularly when first introduced. Defects could result in product recalls, warranty claims, and loss of customer confidence. We maintain product liability insurance, but it may not be sufficient to cover all claims.",
        ],
    ),
    (
        None,
        F
        + "Our use of artificial intelligence may create legal, regulatory, and reputational exposure.",
        [
            "We have begun to integrate machine learning features into our widget planning software. Laws governing artificial intelligence, such as the Westland AI Act, are evolving and may impose new obligations on us. If our models produce inaccurate or biased outputs, our customers may lose confidence in our products.",
        ],
    ),
    (
        None,
        F + "We may not be able to attract and retain qualified personnel.",
        [
            "Our success depends on the continued service of our senior management and engineering teams. Competition for qualified personnel in Widget City is intense. If we are unable to attract and retain employees, our product development efforts could be delayed. We rely on equity awards to compensate employees, and a decline in our stock price could reduce their retention value.",
        ],
    ),
    (
        None,
        F + "We may be unable to protect our intellectual property.",
        [
            "We rely on a combination of patents, trade secrets, and contractual provisions to protect our technology. Our patents may be challenged, invalidated, or circumvented. In fiscal 2025, Omnicorp filed a lawsuit in the Eastland Commercial Court alleging that our WidgetPro line infringes three of its patents. Third parties may assert that our products infringe their intellectual property rights, which could result in costly litigation or require us to obtain licenses on unfavorable terms.",
        ],
    ),
    (
        None,
        F + "Climate change and related regulation could affect our operations.",
        [
            "Extreme weather events could disrupt our facilities and those of our suppliers. New regulations relating to greenhouse gas emissions, including the Westland Climate Disclosure Rule adopted in 2024, could increase our compliance costs. Customers may also require us to meet sustainability standards that increase our expenses.",
        ],
    ),
    ("Risks Related to Regulation and Legal Matters", None, None),
    (
        None,
        F
        + "Changes in trade policy, including tariffs, have increased and could further increase our costs.",
        [
            "Tariffs on imported components increased our cost of goods sold by approximately 3% in fiscal 2025. We may be unable to pass these costs on to customers. Additional tariffs announced by the Westland Trade Commission in March 2025 could apply to our products. Changes in export control regulations could also limit the markets in which we sell our products.",
        ],
    ),
    (
        None,
        F + "We are subject to environmental regulations that could increase our costs.",
        [
            "Our operations are subject to laws governing the use, storage, and disposal of hazardous materials. Compliance with these laws, including the Westland Clean Manufacturing Act, requires ongoing expenditures. Failure to comply could result in fines, suspension of production, or litigation.",
        ],
    ),
    ("Risks Related to Financial Matters", None, None),
    (
        None,
        F + "Fluctuations in foreign currency exchange rates could adversely affect our results.",
        [
            "Approximately 30% of our revenue is denominated in currencies other than the U.S. dollar. We use forward contracts to hedge a portion of this exposure, but hedging may not be effective.",
        ],
    ),
    (
        None,
        F + "Our indebtedness could limit our flexibility.",
        [
            "As of January 26, 2025, we had $3.5 billion of senior notes outstanding, including $1.5 billion issued in June 2024. Our debt agreements contain covenants that restrict our ability to incur additional debt and pay dividends. If we fail to comply with these covenants, our lenders could accelerate repayment, which would harm our liquidity.",
        ],
    ),
    (
        None,
        F + "Changes in tax laws could affect our effective tax rate.",
        [
            "We are subject to income taxes in the U.S. and numerous foreign jurisdictions. Changes in tax laws, including the implementation of a global minimum tax, could increase our effective tax rate. Tax authorities may also challenge our transfer pricing arrangements, e.g. with respect to intercompany licensing.",
        ],
    ),
]


def render(fy: int, period: str, risks: list, acc: str) -> str:
    name = "FIXTURE Example Widgets Corp"
    header = f'<div style="text-align:center;font-size:8pt">{name} | {fy} Form 10-K</div>'
    parts: list[str] = []
    parts.append("<html><head><title>FIXTURE 10-K</title></head><body>")
    parts.append(
        f'<div style="display:none"><ix:header><ix:hidden><ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="c-1">{fy}</ix:nonNumeric>'
        f'<ix:nonNumeric name="dei:DocumentType" contextRef="c-1">10-K</ix:nonNumeric><ix:nonNumeric name="dei:DocumentPeriodEndDate" contextRef="c-1">{period}</ix:nonNumeric>'
        "</ix:hidden></ix:header></div>"
    )
    parts.append(
        '<div style="text-align:center"><span style="font-weight:700">UNITED STATES SECURITIES AND EXCHANGE COMMISSION</span></div>'
    )
    parts.append(
        '<div style="text-align:center"><span style="font-weight:700">FORM 10-K</span></div>'
    )
    parts.append(
        f'<div style="text-align:center"><span style="font-weight:700">{name}</span></div>'
    )
    parts.append(
        f"<p>For the fiscal year ended {period}. Commission file number 000-FIXTURE. Accession {acc}.</p>"
    )
    parts.append(
        '<hr/><p style="text-align:center"><span style="font-weight:700">TABLE OF CONTENTS</span></p>'
    )
    toc = [
        ("Item 1.", "Business", 4),
        ("Item 1A.", "Risk Factors", 9),
        ("Item 1B.", "Unresolved Staff Comments", 22),
        ("Item 1C.", "Cybersecurity", 22),
        ("Item 2.", "Properties", 23),
        ("Item 3.", "Legal Proceedings", 23),
        ("Item 7.", "Management’s Discussion and Analysis", 25),
        ("Item 7A.", "Quantitative and Qualitative Disclosures About Market Risk", 40),
    ]
    parts.append("<table>")
    for num, title, page in toc:
        parts.append(
            f"<tr><td><span>{num.replace(' ', '&#160;')}</span></td><td><a href='#'>{title}</a></td><td>{page}</td></tr>"
        )
    parts.append("</table>")

    def page_break(n: int) -> str:
        return f'<hr style="page-break-after:always"/><div style="text-align:center">{n}</div><div><a href="#toc">Table of Contents</a></div>{header}'

    parts.append(page_break(3))
    parts.append('<p><span style="font-weight:700">PART I</span></p>')
    parts.append('<p><span style="font-weight:700">Item&#160;1. Business</span></p>')
    parts.append(
        f"<p>{name} designs widgets for industrial customers. We were incorporated in Westland in 1998. Our products are sold through distributors and directly to original equipment manufacturers. For a discussion of risks, see Item 1A. Risk Factors below.</p>"
    )
    parts.append(
        "<p>We had approximately 12,000 employees as of the end of fiscal {fy}. Our principal executive offices are located in Widget City, Westland.</p>".replace(
            "{fy}", str(fy)
        )
    )
    parts.append(page_break(8))
    parts.append(
        '<p><span style="font-weight:700">Item&#160;1A.</span><span style="font-weight:700">&#160;Risk&#160;Factors</span></p>'
    )
    parts.append(
        "<p>Investing in our securities involves a high degree of risk. You should carefully consider the risks described below together with the other information in this report. The occurrence of any of the following risks could materially harm our business, financial condition, and results of operations.</p>"
    )
    page = 9
    for i, (group, heading, body) in enumerate(risks):
        if group:
            parts.append(f'<p><span style="font-weight:700;font-style:italic">{group}</span></p>')
            continue
        parts.append(f'<p><span style="font-weight:700">{heading}</span></p>')
        for para in body:
            parts.append(f"<p><span>{para}</span></p>")
        if i % 4 == 3:
            page += 1
            parts.append(page_break(page))
    parts.append(
        '<p><span style="font-weight:700">Item&#160;1B. Unresolved Staff Comments</span></p><p>None.</p>'
    )
    parts.append(
        '<p><span style="font-weight:700">Item&#160;1C. Cybersecurity</span></p><p>Our board oversees cybersecurity risk through its audit committee. We have not identified any cybersecurity incident that materially affected us.</p>'
    )
    parts.append(
        '<p><span style="font-weight:700">Item&#160;2. Properties</span></p><p>Our headquarters consist of 400,000 square feet of owned office space in Widget City.</p>'
    )
    parts.append(
        '<p><span style="font-weight:700">Item&#160;7. Management’s Discussion and Analysis of Financial Condition and Results of Operations</span></p>'
    )
    parts.append(
        "<p>Our results are subject to the factors described in Item 1A. Risk Factors of this report. Revenue increased during the year primarily due to higher unit volumes.</p>"
    )
    parts.append(
        '<p><span style="font-weight:700">Item&#160;7A. Quantitative and Qualitative Disclosures About Market Risk</span></p><p>See the discussion under Item 1A.</p>'
    )
    parts.append("</body></html>")
    return "\n".join(parts)


def main() -> int:
    old = render(2024, "January 28, 2024", OLD_RISKS, "0000000000-24-000001")
    new = render(2025, "January 26, 2025", NEW_RISKS, "0000000000-25-000001")
    (HERE / "FIXTURE_10K_FY2024.htm").write_text(old, encoding="utf-8")
    (HERE / "FIXTURE_10K_FY2025.htm").write_text(new, encoding="utf-8")
    print("wrote FIXTURE_10K_FY2024.htm and FIXTURE_10K_FY2025.htm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
