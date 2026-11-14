# Deploy and verification (Phase 5)

Written 2026-11-14. Live service: https://document-classifier-5fn6.onrender.com (Render free web service, one Docker container: FastAPI serves the API and the built UI).

Claim labels: **confirmed** (source named), **inferred**, **unknown**.

## Decisions taken at the start of Phase 5 (project owner, 2026-11-14)

| Question | Answer |
|---|---|
| Uploaded files vs the PDF view | Random document ids, and uploads are kept on the instance's disk until it sleeps (not deleted after classification) |
| Gzip | Yes (`GZipMiddleware`) |
| Approve marks a document reviewed | Yes |
| TC5 | Left out of the seed. Its PDF shows an account name (`eval/README.md:57`) and is not scored |
| Seed source | One live run of the real pipeline on TC1-TC4, saved as `backend/seed_data.json` |
| Render setup | `render.yaml` Blueprint; the API key typed into the dashboard |

## What was built

| Piece | Where | Notes |
|---|---|---|
| Node 24 UI stage | `Dockerfile` | `npm ci && npm run build` in `frontend/`, `frontend/out` copied into the Python image; the server binds `$PORT` (Render default 10000, https://render.com/docs/web-services) |
| Guard rails | `backend/guard.py`, `backend/main.py`, `backend/config.py` | per-IP 5 uploads/hour; global 100 uploads/day (UTC); 10 MB file; 25-page PDF; 200 MB total stored; client filename cleaned for display (the saved file already had a generated name); one classification per upload (a second call returns 409) |
| Unguessable ids | `Document.public_id` (uuid hex) | every URL and API response uses it; the integer id is internal |
| Seed on boot | `backend/seed.py`, `backend/seed_data.json` | loads only into an empty database; export command is in the module docstring |
| Worker thread | `backend/main.py` | classification runs in `run_in_threadpool`; it took 8 to 34 s on the event loop before |
| One page at a time | `backend/services/document_processor.py` | see "Two defects found before deploy" |
| Gzip, approve-reviewed | `backend/main.py` | |
| Notices | `frontend/app/page.tsx`, `frontend/app/document/page.tsx` | uploads and reviews are visible to everyone and erased on sleep |
| Blueprint | `render.yaml` | free plan, `/health`, `autoDeployTrigger: "off"`, non-secret settings |
| Playwright | `e2e/` | `E2E_UPLOAD=1 BASE_URL=<url> npx playwright test` |

Docs read before the code: https://render.com/docs/blueprint-spec, https://render.com/docs/web-services, https://render.com/docs/health-checks, https://render.com/docs/free, https://playwright.dev/docs/browsers, https://playwright.dev/docs/api/class-locator (the last page was only partly readable; `setInputFiles` and `toContainText` are used from memory and the run exercised both), https://developers.cloudflare.com/fundamentals/reference/http-headers/.

## Two defects found before deploy

| Defect | Evidence | Fix |
|---|---|---|
| **Out of memory on a 512 MB instance.** `convert_from_path(dpi=200)` rendered every page into memory at once. | Confirmed: a container with `--memory 512m --memory-swap 512m` was OOM-killed (`docker inspect` `OOMKilled=true`) on the first upload of TC4 (18 pages). With swap allowed it showed 505 MiB in `docker stats`. Render's free plan is 512 MB / 0.1 CPU (https://render.com/docs/compute-plans, seen in a search result; the pages I fetched directly did not list it). Whether Render allows swap is **unknown** | One page per call (`first_page=last_page`). Same limits: TC1-TC4 classified in sequence, peak 288,022,528 bytes (`memory.peak`), no OOM, labels unchanged |
| **The event loop was blocked** for the length of each classification, while Render's health check allows 5 s and stops routing after 15 s of failures (https://render.com/docs/health-checks) | Confirmed in the code (`classify_document` was called directly inside an `async def`) | `run_in_threadpool` |

Local cold start at 0.1 CPU: about 25 s from container start to "Seeded 4 documents" (confirmed: container log timestamps).

## Playwright on the live URL

Command: `E2E_UPLOAD=1 BASE_URL=https://document-classifier-5fn6.onrender.com npx playwright test` (Chrome via `channel: 'chrome'`, serial, one worker). Final run, on the service after the env change below: **12 passed, 2.3 min**.

| Check | Result |
|---|---|
| `/health` answered | after 0.2 s (service already awake) |
| Queue lists TC1-TC4 once each, shows model `claude-haiku-5-5` and the sleep notice | pass |
| Seeded TC1 | Public, Safe, 4 citations with the quote found on the cited page; PDF page drawn |
| Seeded TC2 | Highly Sensitive, Safe, 2 such citations |
| Seeded TC3 | Confidential, Safe, 2 such citations |
| Seeded TC4 | Confidential, Safe, 1 such citation |
| PDF.js worker | 200, `content-encoding: gzip` |
| `/api/documents/1` and `/1/file` | 404 |
| Upload TC1 through the UI | Public, Safe, 4 citations with the quote found (45.6 s including the PDF view) |
| Upload TC2 | Highly Sensitive, Safe, 1 such citation (19.3 s) |
| Upload TC3 | Confidential, Safe, 2 such citations (15.7 s) |
| Upload TC4 | Confidential, Safe, 1 such citation (37.1 s) |
| Per-IP limit | statuses 200, 429, 429 after the four uploads; a forged `X-Forwarded-For` also 429 |

All eight labels match `eval/golden.csv`. `unsafe` is false for all, which is what the golden file says for TC1-TC4. "Valid citation" here means the UI ticked the chip: the quoted text was found in the extracted text of the cited page (`verified`, from the classifier's own check). **TC5 was not run**: it is out of the seed (decision above) and its golden label is not scored (`eval/README.md`, decision 3). The plan's "upload TC1-TC5" is therefore TC1-TC4 here.

### What failed on the way (kept, because it bears on the demo)

| When | What | Reading |
|---|---|---|
| First live run | Upload TC2: the model's reply could not be parsed ("model returned no valid sensitivity: 'Unknown'"); the row is `failed` | One failure; the seed export had the same failure once on TC2 (a container run). Eight consecutive local runs of TC2 all passed. Cause **unknown**: the raw reply was not logged |
| Second live run | Upload TC2 classified Highly Sensitive but **none** of its citations had the quote found | Matches the eval's "at least one valid citation" rate of 11/12 on TC1-TC4 (`eval/runs_phase3/combo/metrics.md`). Seeded TC2 has two |
| Second live run | The per-IP limit never answered 429 in 9 uploads | Confirmed. The key was the last `X-Forwarded-For` entry; Render's service sits behind Cloudflare (response headers `Server: cloudflare`, `CF-RAY`), which appends each hop, so that entry was not the visitor (inferred from https://developers.cloudflare.com/fundamentals/reference/http-headers/) |

Fix: `CLIENT_IP_HEADER=cf-connecting-ip`, set in the Render dashboard (and in `render.yaml`). Then the limit worked (table above). A forged `cf-connecting-ip` header from my machine was answered **403** (confirmed with curl; Cloudflare rejected it before the app), and forged `x-forwarded-for` and `x-real-ip` headers were answered 429. Whether every visitor gets a separate bucket could only be checked from one network: **unknown** for a second visitor, though the header is documented to hold the visitor's address.

**Reliability of a visitor's own upload:** nine upload classifications ran on the live service (TC1 x2, TC2 x3, TC3 x2, TC4 x2). One failed to parse (TC2) and one had no ticked citation (TC2). A failure rate near 10% is **inferred** from that small sample, not measured. The seeded rows are not affected.

## Cold start

About 32 s for the first request after 17 idle minutes (one measurement, see the end of this file).

## Cost

About 9 live classifications ($0.002 each, **inferred** from `eval/runs_phase3/combo/metrics.md`, the API does not return cost) plus about 30 local ones: well under $0.15. The spend cap in the Anthropic Console is the backstop; it is set by the project owner.

## Known limits

- **Uploads are public to every visitor** until the instance sleeps. Random ids stop id-guessing but `GET /api/documents` lists every id, so anyone can open anyone's upload. The notice on the queue says so. A queue scoped per visitor would change this (not built).
- **Counters are in memory.** A restart resets the per-IP and daily counts, and wipes uploads, feedback and reviews (Render's disk is ephemeral, https://render.com/docs/free). Seeded rows come back.
- **Feedback does not survive a sleep.** The UI says so.
- **Wake-up:** a free instance sleeps after 15 idle minutes (https://render.com/docs/free).
- **Not measured:** Render's outbound bandwidth allowance (the docs page gives no figure), PDF.js worker timing on Render from a slow link, behaviour with two simultaneous classifications at 0.1 CPU, Lighthouse on the live URL.
- **Only the seeded documents are cited as evidence of correctness.** Uploads are shown to work, not to be reliable (see the failure table).

## Adjacent issues (listed, not fixed)

1. The model sometimes returns text that is not valid JSON; `_parse_classification_response` then falls back to "Unknown" and the document fails. Logging the raw reply, and one retry, would diagnose and likely hide it.
2. A failed classification cannot be retried: the document is `failed` and a second call returns 409. The visitor re-uploads and uses quota.
3. `/api/feedback` still turns its own 404 into a 500, takes query parameters, and has no length limit on `comments`.
4. Classify errors still return `technical_error` (raw exception text) to the client.
5. No cap on simultaneous classifications; at 0.1 CPU two at once are untested.
6. The queue says "Classified" for rows that are neither reviewed nor flagged; no seeded row needs review (TC4's confidence 0.72 is above the 0.7 threshold).
7. `shadcn` still sits in `dependencies` (UI_BUILD.md, item 14).
8. This file is not linked from the README.

## Teach-back kit

Purpose: check that a reviewer who has never seen the tool can read a result, find the evidence, and decide. Run on the live URL (open it once first so the instance is awake). Three seeded documents, no upload needed.

**Task, same for each document:** "Open this document. Decide whether you would approve the label or override it, and say why in one sentence. Point to the evidence you used."

Give no hints about the page chips or the buttons.

| # | Document | Label shown | Expected decision | Expected reason (any of) | Evidence to find |
|---|---|---|---|---|---|
| 1 | `TC1_Sample_Public_Marketing_Document.pdf` | Public, Safe | Approve | A product brochure: services, pricing models, partner offers, customer testimonials; no personal records or internal content | A ticked chip on p.2, 3, 5 or 7 (e.g. p.2 "The Hitachi EverFlex Infrastructure as a Service (IaaS) portfolio is the answer...") |
| 2 | `TC2_Filled_In_Employement_Application.pdf` | Highly Sensitive, Safe | Approve | A completed application for an identified person: name, addresses, phones, employment and education history, conviction questions | Ticked chip p.1 ("Name (Last, First, Middle) Simmons, Susan J.") or p.2 (employment history) |
| 3 | `TC4_ Stealth_Fighter_With_Part_Names.pdf` | Confidential, Safe (confidence 0.72) | Approve | An aviation flight-operations manual template with company policies and procedures; no personal data, nothing classified. Confidential follows the docx line "Confidential (policy-based)" and the owner's decision 1 in `eval/README.md` | Ticked chip p.4 ("Company/Organization Name encourages feedback ...") |

Source of the expected decisions: `eval/golden.csv` (the labels the model also produced) and the seeded summaries in `backend/seed_data.json`. All three expected decisions are approvals, so the kit tests reading and evidence-finding more than disagreement. A reviewer who overrides document 3 to Highly Sensitive (the docx's Highly Sensitive definition names military schematics) is giving a defensible answer that differs from the project's decision; record it as "overrode, reason given" and do not mark it wrong. None of the seeded documents is one the model gets wrong, so there is no override probe; add one by uploading a document the model mislabels, if you find one.

**Rubric (per document):**

| Measure | How to score |
|---|---|
| Time to decision | Seconds from opening the document view to pressing Approve or Override (screen recording or a stopwatch). Target under 90 s after the first document |
| Found the evidence | Yes if the participant names a page and a quote (or clicks a citation chip) that supports their reason; no if they give a reason without pointing to anything |
| Decision matches expected | Yes / No, plus the reason they gave |
| Understood the ticks | Ask once at the end: "What does the tick on a page chip mean?" Expected: the quoted text was found on that page |
| Understood the limits | Ask once: "What happens to your review tomorrow?" Expected: it is gone, the demo sleeps and forgets |

Record per participant: the three times, three yes/no's, any chip they could not read. Scoring is by hand; nothing in the app records it.

## Idle wake-up measurement

One measurement (2026-11-14, from the project owner's network): no request to the service for about 17 minutes (the last was at 02:29 local time; the free plan spins down after 15 idle minutes, https://render.com/docs/free), then `curl` for `/`:

| Request | Result |
|---|---|
| First, at 02:46:46 | HTTP 200 after **32.5 s** (`time_total`) |
| Second, right after (`/health`) | HTTP 200 after 0.4 s |

Render's docs say "about one minute" to spin up; this one took about half that. A single run, so the spread is **unknown**. That the instance had really spun down is **inferred** from the 32 s delay; the dashboard was not checked. The Playwright spec's wake-up poll allows 170 s.
