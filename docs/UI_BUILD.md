# UI build (Phase 4b: Phase 4 steps 2 to 4)

Written 2026-11-14. Builds the two screens approved in `docs/UI_LIB.md` and records the accessibility check, Lighthouse scores and PDF.js worker timing. Nothing here is deployed; every number is from this machine against a local container (Phase 5 measures the live service).

Claim labels: **confirmed** (source named), **inferred**, **unknown**.

## Decisions taken at the start of 4b (by the project owner, 2026-11-14)

| Question | Answer |
|---|---|
| Stack | Current Next with React 19, react-pdf 11, Tailwind 4; unused dependencies removed from `frontend/package.json` |
| Node for the Docker frontend build stage | **Node 24**, recorded only; the stage is added in Phase 5. react-pdf 11 needs Node 22.13 or newer (confirmed: react-pdf README). The build here ran on Node v24.18.1 |
| Backend changes | Approved: PDF file route, store and return `verified`, serve the export at `/`, model name in `GET /api`, delete the old `frontend/public/index.html` |
| Seed rows for the queue | TC1-TC4 classified once through the local API. TC5 left out: its capture shows an account name (`eval/README.md:57`) |

## What was built

Two screens, served by FastAPI as a static export (one process).

- **Review queue** (`frontend/app/page.tsx`, `/`): header strip with the model name (from `GET /api`) and four eval figures. The queue has sortable columns (document, label, safety, status, confidence, added) and filters by name and label. The upload control carries the notice "Do not upload real personal data", then uploads and classifies the file.
- **Document view** (`frontend/app/document/page.tsx`, `/document/?id=N`): the PDF on the left (`frontend/components/pdf-pane.tsx`, react-pdf, loaded with `ssr: false`, `workerSrc` set in the same module). The right panel shows label, safety, confidence, reasons and citations. Clicking a citation jumps to its page and marks the quote on the page as best effort; the quote text is always shown in the panel. Approve posts `feedback_type=confirmation`. Override posts `feedback_type=correction` with the new sensitivity and safety and an optional note.
- **Signature:** the mono citation chip `p.13` with a tick when the quote was found on that page (`PageChip` in `frontend/components/bits.tsx`). Chips without a tick say "Quote not found in this page's extracted text".
- **Design tokens** (`frontend/app/globals.css`): a barely warm grey ramp (page `#f6f5f2`, card `#fdfcfa`, raised `#eeece7`, text `#1f1d1a` / `#55504a` / `#6b665e`), one redline `#9e3328` used only for Highly Sensitive, unsafe, errors and the selected citation. Focus ring `#1f1d1a` at 50%, about 3.2:1 on the card (inferred: my contrast arithmetic). Geist and Geist Mono, weights 400 and 500, sentence case, 4px grid, colour-only transitions. Icons are lucide at 16px with stroke 1.5; the one exception is the tick inside the citation chip, 12px with stroke 2.
- **Choices made during the build, not asked:** the upload control accepts PDF only; the reviewer name is fixed; the eval figures are constants.

Eval figures in the header strip come from `eval/runs_phase3/combo/metrics.md` and `docs/FEATURES.md` (confirmed): TC1-TC4 12/12 correct (vs 3/12 with the previous prompt), false-Public 0% (vs 67%), synthetic 63/72, quote found on the cited page 28/91 (31%). They are constants in `frontend/app/page.tsx`, not read from the API.

### Installed (confirmed: `frontend/package.json`)

`next` 16.4.6, `react` / `react-dom` 19.3.1, `react-pdf` 11.0.0 (bundles `pdfjs-dist` 6.3.289), `@tanstack/react-table` 9.3.1, `lucide-react` 1.73.0, `tailwindcss` / `@tailwindcss/postcss` 4.3.5, `typescript` ^5, `@types/*`. `shadcn init` (4.23.0, preset Nova, Radix base) added `class-variance-authority`, `cn` (published from `shadcn-ui/cn`, confirmed: `npm view cn`), `radix-ui`, `shadcn` and `tw-animate-css`. shadcn components copied in: button, input, table, native-select. Lighthouse 13.6.0 and axe-core 4.14.0 ran through `npx` / `npm pack` only and are not saved.

### Docs read before the code

- Next.js static exports: https://nextjs.org/docs/app/guides/static-exports (updated 2026-08-09). `output: 'export'`, `trailingSlash` emits `/document/index.html`
- Next.js app icons: https://nextjs.org/docs/app/api-reference/file-conventions/metadata/app-icons (`app/icon.svg`)
- react-pdf README: https://github.com/wojtekmaj/react-pdf/blob/main/packages/react-pdf/README.md
- shadcn Next install and data table guide: https://ui.shadcn.com/docs/installation/next, https://ui.shadcn.com/docs/components/radix/data-table (TanStack Table v9: `tableFeatures`, `useTable`, `createSortedRowModel`). The v9 exports were checked in the installed type definitions too

### Backend changes (`backend/main.py`, `backend/models/classification.py`)

- `GET /api/documents/{id}/file` returns the stored upload; 404 when the row or file is missing. The `Content-Type` comes from the stored file's extension, which upload has already checked against the allow-list. It is never the type the uploader claimed, and the response carries `X-Content-Type-Options: nosniff`. Without this, a file named `x.pdf` uploaded as `text/html` would have been served as HTML on the app's origin (inferred from the code; the first version stored `file.content_type` and served it back). The test asserts the fix.
- `citation_evidence.verified` (Boolean, nullable) is saved from the classifier's existing flag (`backend/services/classifier.py:469`) and returned in `GET /api/documents/{id}`. `null` means not checked (PII and image citations). **A SQLite file created before this change has no such column; delete it and let `init_db()` recreate it** (there are no migrations).
- `GET /api` adds `"model"`.
- The old `/` route and `/static` mount are gone; `frontend/out` is mounted at `/` with `StaticFiles(html=True)` after every API route, only if the folder exists.
- Test: `test_ui_endpoints_serve_file_verified_flag_and_model` in `test_system.py`.

## Verification run

| Check | Result |
|---|---|
| `python -m pytest -q test_system.py` in `docclf-eval:phase3`, `.env` masked, with `frontend/out` present | 32 passed, 4 xfailed (the pinned known defects) |
| `npm run build` | static export of `/`, `/document`, `/icon.svg`; TypeScript passes |
| Routes on the local container | `/` 200, `/document/` 200, `/document?id=1` 307 to `/document/?id=1` (query kept), `/docs` 200, unknown path 404, worker served as `text/javascript` |
| Seeding: TC1-TC4 through `POST /api/documents/upload` + `/classify` | Public, Highly Sensitive, Confidential, Confidential (all match `eval/golden.csv`), 8 to 14 s each. Cost not returned by the API; about $0.008 at the `combo` arm's mean $0.002 per document (inferred) |
| Browser, desktop | queue sorts (with `aria-sort`) and filters by name and label; upload of a fake PDF shows the server error and a Failed row; citation p.13 on TC4 jumps to page 13 and marks the quote; approve saved feedback #1; override to Public saved #2 and the panel showed Public (restored afterwards) |
| Broken file in the document view | Before the fix, a file that is not a valid PDF crashed the whole view: react-pdf 11 suspends by default and throws load errors to the nearest error boundary (confirmed: installed react-pdf README, "Suspense" section). With `suspense={false}` the pane shows "Could not load this PDF" and the panel says "Classification failed for this file" |
| `npm ci` then `npm run build` in `frontend/` | passes |
| More than 100 documents (PR #6 review) | `GET /api/documents` now orders by id. The queue reads every 100-row page up to `total`: with 106 documents the API's first page held 100, and the queue showed all 106 |

**The seeded rows exist only in the local container's database** (`/tmp/ui.db`). A fresh checkout shows an empty queue until Phase 5 seeds on boot.

How the container was run, for reproduction. The key reaches the container through Docker's `--env-file`, and settings that `.env` might override are pinned with `-e`. The list-typed settings are pinned because the app failed to start with "error parsing value for field ALLOWED_EXTENSIONS". Whether that comes from how `.env` writes the value, or from Docker keeping quotes literally in `--env-file`, is **unknown**. So is whether the app starts with the real `.env` outside Docker; I did not open it.

```bash
cd frontend && npm ci && npm run build && cd ..
docker run -d --name docclf-ui -p 127.0.0.1:8765:8000 --env-file .env -e DATABASE_URL=sqlite:////tmp/ui.db -e UPLOAD_DIR=/tmp/uploads -e PRIMARY_LLM_MODEL=claude-haiku-5-5 -e LLM_INPUT_MODE=text -e PROMPT_PII_HINTS=false -e PROMPT_FAIL_CLOSED=true -e PROMPT_WIDE_HS=true -e USE_DUAL_VERIFICATION=false -e MAX_TOKENS=4096 -e 'ALLOWED_ORIGINS=["http://localhost:8765"]' -e 'ALLOWED_EXTENSIONS=["pdf","png","jpg","jpeg","tiff","doc","docx"]' -e 'CLASSIFICATION_CATEGORIES=["Public","Confidential","Highly Sensitive"]' -v "$PWD":/app -v <empty-file>:/app/.env:ro -w /app docclf-eval:phase3 uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Accessibility

- **axe-core 4.14.0**, tags WCAG 2.0/2.1/2.2 A and AA plus best-practice, Chrome headless, on six states: queue, document, and document with a citation selected and the override form open, each at 1440 and 375 px. **0 violations in all six** after one fix (below).
- **Fixed during the check:** `scrollable-region-focusable` (serious) on the PDF scroll area at desktop width. It is now focusable with a visible ring.
- **Incomplete, not a defect:** `color-contrast` could not be decided for 18 nodes on the document view. All are PDF.js text-layer spans: transparent text over the page canvas that makes selection and highlighting work. The visible text is the PDF image itself. Every app element passed `color-contrast`.
- **Fixed during the check:** the focus ring was `#55504a` at 50%, about 2.4:1 on the card against WCAG 1.4.11's 3:1 (inferred: my arithmetic; axe does not test focus indicators). It is now `#1f1d1a`, checked by eye on a focused sort button.
- **Keyboard:** tabbing the queue reaches the wordmark, file input, upload button, both filters, the six sort buttons and each document link, in that order, each with a visible focus indicator (checked from computed `box-shadow`/`outline`).
- **Lighthouse accessibility:** 100 on both screens, mobile and desktop.
- **Not tested:** a real screen reader (unknown how NVDA or VoiceOver announce the citation buttons), and forced-colours mode.

## Lighthouse

Lighthouse 13.6.0, HeadlessChrome 157, local container on `localhost`, so network time is near zero and the mobile figures come from Lighthouse's simulated throttling. Document view measured on TC4 (18 pages).

Final run on the final build:

| Screen, preset | Performance | Accessibility | Best practices | SEO | FCP | LCP | TBT | CLS |
|---|---|---|---|---|---|---|---|---|
| Queue, mobile | 77 | 100 | 100 | 100 | 1.1 s | 5.3 s | 210 ms | 0.007 |
| Queue, desktop | 100 | 100 | 100 | 100 | 0.3 s | 0.3 s | 0 ms | 0.008 |
| Document, mobile | 68 | 100 | 100 | 100 | 0.9 s | 4.7 s | 570 ms | 0 |
| Document, desktop | 95 | 100 | 100 | 100 | 0.3 s | 1.6 s | 20 ms | 0 |

Performance varies run to run; every other category was 100 in every run after the icon fix. Across all five runs (three on an earlier build, two on later builds), the ranges were:
- queue mobile 77 to 82;
- queue desktop 100;
- document mobile 56 to 80;
- document desktop 94 to 95.

The document mobile score moves with total blocking time (200 to 570 ms), which comes from PDF.js parsing and drawing the page on a 4x-throttled CPU (inferred).

The first run had best practices at 96 because `/favicon.ico` returned 404. `frontend/app/icon.svg` fixed it.

## PDF.js worker load

The worker is emitted as `out/_next/static/media/pdf.worker.min.*.mjs`, **1,265,413 bytes**. FastAPI's `StaticFiles` serves it uncompressed; gzipped it would be 375,379 bytes (confirmed: `gzip -c | wc -c`).

Measured with puppeteer-core in headless Chrome, cold cache, 3 runs per profile, `/document/?id=4` (script kept outside the repo):

| Profile | Worker request starts | Worker download | PDF download (456 KB) | First page drawn |
|---|---|---|---|---|
| No throttling (local) | 0.51 to 0.59 s | 17 to 27 ms | 6 to 9 ms | 0.63 to 0.76 s |
| Lighthouse mobile network (150 ms RTT, 1.6 Mbps down) and 4x CPU | 8.3 to 8.8 s | 6.04 to 6.07 s | 2.33 to 2.34 s | 17.0 to 17.6 s |

Reading:
- On a slow mobile link the uncompressed worker alone takes about 6 s, and it only starts after the 655 KB react-pdf chunk has loaded.
- The panel (label, reasons, citations and quotes) renders from the API before the PDF arrives, so a reviewer can read the evidence while the page image loads.
- Render free-tier bandwidth is unknown; Phase 5 should measure there.

## Adjacent issues (listed, not fixed)

1. **No compression.** `GZipMiddleware` (Starlette built-in) would cut the worker from 1.27 MB to about 375 KB, and the JS similarly (inferred from the gzip measurement). A one-line backend change; a Phase 5 candidate.
2. **The worker is requested late.** It is only fetched after the react-pdf chunk loads. A preload hint could overlap them (inferred, untested).
3. **Approve does not mark a document reviewed.** `/api/feedback` updates the document only on a correction (`backend/main.py`), so an approved row still reads "Needs review" or "Classified" in the queue.
4. **`/api/feedback` errors.** It takes query parameters, and `except Exception` turns its own 404 for a missing document into a 500.
5. **Raw server messages.** Upload and classify errors show the backend text as is, for example "EOF marker not found".
6. **Highlight false positives.** The highlight marks whole text items that occur inside the quote, so a short line can be marked by mistake (seen: "security." on TC4 page 13). Quotes split across items are marked in part.
7. **`.gitignore` line 13 (`lib/`) ignores `frontend/lib/`.** `shadcn init` wrote `frontend/lib/utils.ts`, which would not be committed, so the app imports `cn` from the `cn` package directly, as the shadcn components already do. The ignored file is unused; `components.json` still names `@/lib/utils` as the alias.
8. **The UI accepts PDF only;** the backend still accepts images and Word files. The document view shows PNG/JPEG with a plain `<img>` and says "No preview" for other types.
9. **Fixed reviewer name.** Feedback rows carry `reviewer_name = "demo reviewer"`; there are no accounts.
10. **Leftover import.** `HTMLResponse` is now unused in `backend/main.py`.
11. **The Dockerfile has no Node stage yet** (Phase 5, Node 24). `next/font/google` downloads Geist at build time, so that stage needs network access (inferred).
12. **Generated files.** `frontend/next-env.d.ts` and `frontend/tsconfig.tsbuildinfo` are generated by `next build`; the existing `.gitignore` does not list them.
13. **Phase 5 conflict, your decision.** PLAN Phase 5 says uploaded files are deleted after classification, but the document view needs the stored file to show the PDF. `GET /api/documents/{id}/file` is also readable by anyone who guesses a sequential id. Options include keeping files until the instance sleeps, or random ids.
14. **`npm audit`:** 6 findings (2 low, 4 moderate), all in the dependencies of the `shadcn` CLI package (`ts-morph`, `minimatch`, `deepmerge` and others). `shadcn init` listed `shadcn` as a runtime dependency because `globals.css` imports `shadcn/tailwind.css`. I infer none of it reaches the browser bundle; moving it to `devDependencies` is untested.
15. **The broken-file view still shows the page controls** ("Page 1 of …") above "Could not load this PDF".
