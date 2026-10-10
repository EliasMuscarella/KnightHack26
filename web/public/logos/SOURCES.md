# Logo sources

Downloaded once at development time from Wikimedia Commons (no runtime requests). Each file was
sanitized: XML declaration, DOCTYPE, comments, metadata, editor namespaces, `id`s, `<title>`/`<desc>`
removed; no `<script>`, `<image>`, `<foreignObject>`, `on*` attributes or external references remain;
coordinates rounded to 3 decimals. The artwork itself is unchanged. The logos are trademarks of their
owners and identify the company whose filings are shown.

| File | Company | Source |
|---|---|---|
| `AAPL.svg` | Apple | https://commons.wikimedia.org/wiki/File:Apple_logo_black.svg |
| `AMZN.svg` | Amazon | https://commons.wikimedia.org/wiki/File:Amazon_icon.svg |
| `NVDA.svg` | NVIDIA | https://commons.wikimedia.org/wiki/File:NVIDIA_logo.svg |
| `CRWD.svg` | CrowdStrike | https://commons.wikimedia.org/wiki/File:CrowdStrike_logo.svg |
| `SF.svg` | Stifel Financial | https://commons.wikimedia.org/wiki/File:Stifel_Financial_logo.svg |

Add a logo: put a genuine file here as `{TICKER}.svg`, record its source above, and add the ticker to
`web/src/lib/logos.ts` (tickers not listed there render a monogram and never request an image).
