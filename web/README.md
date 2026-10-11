# RiskDiff web

Next.js + TypeScript + Tailwind frontend for RiskDiff. Read `../DESIGN.md` before changing anything here.

```bash
npm install
npm run dev          # http://localhost:3000 (expects the API on :8000; see ../scripts/dev.sh)
npm run build
npm run lint
npm run typecheck
npm run test:unit    # node tests in src/lib/__tests__
npm run test:e2e     # Playwright smoke test
```

`src/types/comparison.ts` is generated from `pipeline/schema.py` by `../scripts/regen_contract.py`; never edit it by hand.
