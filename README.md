# Regulatory Document Classifier

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Live demo: https://document-classifier-5fn6.onrender.com. It runs on a free Render instance that sleeps after 15 idle minutes. The first request after a sleep took about 32 s, and the instance erases uploads and reviews when it sleeps. Do not upload real personal data.

Built for the TAMU Datathon 2025 document-classification challenge. It reads a PDF and returns two labels, each with its reasons and page citations:

- **`sensitivity`**: Public, Confidential or Highly Sensitive
- **`unsafe`**: yes or no (child safety, hate speech, exploitation, violence, criminal, political-news or cyber-threat content). It is independent of `sensitivity`.

A reviewer then approves or overrides the label in a small web UI. The model is `claude-haiku-5-5`.

Every number below comes from a recorded run. [`docs/FEATURES.md`](docs/FEATURES.md) and [`docs/VERIFY.md`](docs/VERIFY.md) explain each one and its caveats.

---

## What it does

- The review queue (`/`) lists all documents, sortable and filterable, with an upload control and the evaluation figures.
- The document view (`/document/?id=...`) shows the PDF on one side and the label, safety, confidence, reasons and citations on the other. Clicking a citation jumps to its page. A tick on a page chip means the quoted text was found in that page's extracted text. Approve or override posts feedback.
- The API (Swagger at `/docs`) uploads, classifies, returns results and takes feedback.
- The pipeline extracts text (PyPDF2, with OCR for pages that have none), runs regex PII and content-safety checks, makes one LLM call, attaches page citations, and flags a document for human review when confidence is below 0.7.
- A second-model verification pass (`USE_DUAL_VERIFICATION`) exists but is off by default and was not evaluated.

### Labels

| `sensitivity` | Meaning |
|---|---|
| Public | Marketing material, brochures, public website content |
| Confidential | Internal communications, business documents, customer details, non-public operations |
| Highly Sensitive | SSNs, account or card numbers, proprietary schematics, a private individual's application or personnel file |

Any Highly Sensitive trigger makes a document Highly Sensitive; otherwise any Confidential trigger makes it Confidential; otherwise it is Public (the shipped prompt only says Public on clear evidence). Definitions: `backend/prompts/prompt_library.yaml`.

---

## Measured results

Model `claude-haiku-5-5`, shipped prompt (the `combo` arm), 3 runs each. Source: `eval/runs_phase3/combo/metrics.md`.

| Measure | Result |
|---|---|
| TC1-TC4 labelled correctly | 12/12 (3/12 with the previous prompt) |
| Sensitive documents labelled Public (TC1-TC4) | 0% (0/9) (67% before) |
| Synthetic set (24 documents, labels derived from the challenge text) | 63/72 correct; Highly Sensitive recall 27/27; Public recall 16/24 |
| Quote found on the cited page | 31% on TC1-TC4, 71% on the synthetic set |
| Cost per document | about $0.002 on TC1-TC4 (mean $0.00201), $0.00086 on the synthetic set |
| Time per document | median 14.7 s on TC1-TC4 (including OCR), 6.7 s on the synthetic set |

Citations point to a page, not to a region of the page. The challenge asks for the region of a serial number on TC4 and TC5, and this does not provide it.

---

## Test cases

| Case | Document | Golden label (`eval/golden.csv`) | Notes |
|---|---|---|---|
| TC1 | Public marketing brochure | Public, safe | |
| TC2 | Filled-in employment application | Highly Sensitive, safe | |
| TC3 | Internal memo | Confidential, safe | |
| TC4 | Aviation flight-operations manual template | Confidential, safe | "Confidential (policy-based)" in the challenge text |
| TC5 | Screen capture of a Word web editor | not scored | The PDF does not match its challenge description, and the live seed leaves it out because it shows an account name |

The PDFs are in `HitachiDS_Datathon_Challenges_Package/`.

---

## Run it

### Docker (the deployed image)

```bash
docker build -t docclf .
docker run --rm -p 8000:8000 -e ANTHROPIC_API_KEY=your_key docclf
```

Open http://localhost:8000. The image builds the UI with Node 24, installs tesseract, poppler and libmagic, and seeds TC1-TC4 on first start.

### Without Docker

You need Python 3.12, Tesseract and Poppler on the PATH (`brew install tesseract poppler`, `apt-get install tesseract-ocr poppler-utils libmagic1`, or the Windows builds), and Node 22.13 or newer for the UI.

```bash
pip install -r backend/requirements.txt
cp .env.example .env            # add ANTHROPIC_API_KEY
(cd frontend && npm ci && npm run build)   # serves the UI at /; skip for API only
python -m uvicorn backend.main:app --port 8000
```

On start, the app adds the `public_id` column to a SQLite file made by an older version.

---

## API

Every document id is an unguessable 32-character hex string.

```bash
# 1. upload (returns document_id; nothing is classified yet)
curl -F "file=@document.pdf" http://localhost:8000/api/documents/upload

# 2. classify once (a second call returns 409)
curl -X POST http://localhost:8000/api/documents/<document_id>/classify

# 3. read the result
curl http://localhost:8000/api/documents/<document_id>

# 4. review: approve ("confirmation") or override ("correction"); query parameters
curl -X POST "http://localhost:8000/api/feedback?document_id=<document_id>&feedback_type=correction&reviewer_name=me&corrected_category=Confidential&corrected_unsafe=false&comments=why"
```

Classify returns `sensitivity`, `unsafe`, `confidence`, `summary`, `requires_review` and the document metadata. The document read returns the reviewed values plus `citations` (`page_number`, `evidence_type`, `evidence_text`, `description`, `verified`). `GET /api/documents` lists the queue, `GET /api/documents/<id>/file` returns the stored PDF, `GET /api` names the model, `GET /health` is the health check.

---

## Layout

```
backend/
  main.py            FastAPI app: API routes, serves frontend/out at /
  guard.py           upload quotas, page cap, filename clean-up
  seed.py            loads backend/seed_data.json on first start (also exports it)
  config.py          settings (environment variables)
  models/ database/  SQLAlchemy models and setup
  services/          document_processor, pii_detector, content_safety, classifier, prompt_manager
  prompts/           prompt_library.yaml
frontend/            Next.js static export: review queue and document view
eval/                golden labels, eval runner, recorded runs (see eval/README.md)
e2e/                 Playwright spec for a deployed URL
docs/                FAILURES, FEATURES, UI_LIB, UI_BUILD, VERIFY, ARCHITECTURE
test_system.py       pytest suite (the Anthropic call is faked)
Dockerfile           Node 24 UI stage + Python image
render.yaml          Render Blueprint (free plan)
```

---

## Configuration

Settings are environment variables (defaults in `backend/config.py`); `.env.example` lists the common ones.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | required to classify |
| `PRIMARY_LLM_MODEL` | `claude-haiku-5-5` | |
| `USE_DUAL_VERIFICATION` | `False` | needs `OPENAI_API_KEY`; not evaluated |
| `LLM_INPUT_MODE` | `text` | `pdf_*` modes exist but did not pass the ship gate (`docs/FEATURES.md`) |
| `LOW_CONFIDENCE_THRESHOLD` | `0.7` | below this a document is flagged for review |
| `MAX_FILE_SIZE_MB`, `MAX_PDF_PAGES`, `MAX_STORED_MB` | 10, 25, 200 | upload caps |
| `UPLOADS_PER_IP_PER_HOUR`, `UPLOADS_PER_DAY` | 5, 100 | upload quotas, counted in memory |
| `CLIENT_IP_HEADER` | empty | set to `cf-connecting-ip` behind Cloudflare (Render) |
| `SEED_ON_BOOT` | `True` | load the TC1-TC4 results into an empty database |
| `DATABASE_URL`, `UPLOAD_DIR` | SQLite file, `uploads` | |

Lists such as `ALLOWED_EXTENSIONS` are JSON when set in the environment: `ALLOWED_EXTENSIONS=["pdf"]`.

---

## Tests

```bash
# unit and API tests (needs tesseract, poppler, libmagic: easiest inside the image)
docker run --rm -v "$PWD":/app -w /app docclf python -m pytest -q test_system.py

# paid eval against the golden labels (subcommands: estimate, run; see eval/README.md)
python eval/run_eval.py --help

# deployed service
cd e2e && npm ci && BASE_URL=https://your-service E2E_UPLOAD=1 npx playwright test
```

`E2E_UPLOAD=1` uploads TC1-TC4 through the UI, which spends API calls and uses the per-IP quota.

---

## Limits and security

- Uploads are visible to every visitor until the instance sleeps. Random ids stop id-guessing, but the queue lists every document.
- The server enforces per-IP and daily upload caps, size, page and storage caps, one classification per upload, and a generated name for every stored file. Display filenames are cleaned.
- Counters live in memory and files on an ephemeral disk, so a restart clears uploads, reviews and quota counts. Seeded results return.
- About 1 in 10 uploaded documents may fail to parse or come back without a ticked citation (a small sample, see `docs/VERIFY.md`).
- There are no accounts. Feedback is recorded under a fixed reviewer name, and the API has no authentication.
- Known defects and open items are in `docs/FAILURES.md` and the "Adjacent issues" section of `docs/VERIFY.md`.

---

## Deployment

The app runs as one free Render web service (Docker), defined in `render.yaml` (New > Blueprint). You type the API key into the dashboard, and deploys are manual. [`docs/VERIFY.md`](docs/VERIFY.md) records the verification results, the memory and event-loop defects found on the way, and the teach-back kit.

---

## Documentation

- [docs/VERIFY.md](docs/VERIFY.md): deployment, live test results, limits, teach-back kit
- [docs/FEATURES.md](docs/FEATURES.md): the features tried, with deltas and ship verdicts
- [docs/FAILURES.md](docs/FAILURES.md): defects found and fixed
- [docs/UI_LIB.md](docs/UI_LIB.md), [docs/UI_BUILD.md](docs/UI_BUILD.md): UI library choice and build record
- [eval/README.md](eval/README.md): golden labels and how the eval runs
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): system architecture (written early; where it disagrees with the above, the above is current)

---

## Team

**TAMU Datathon 2025 - Team VibeTribe**

## License

MIT. No `LICENSE` file is committed yet.

## Acknowledgments

Anthropic for the Claude API; FastAPI; Tesseract and pdf2image; Next.js, shadcn, TanStack Table and react-pdf.
