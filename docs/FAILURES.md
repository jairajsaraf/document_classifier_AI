# Failure map and fix list (Phase 2)

Written 2026-11-13 on branch `claude/phase-2-fixes-5e3d1d`, which was cut from `plan/eval-and-deploy` at `9d25598`. The baseline is `eval/runs/` (3 runs × 28 scored documents). Its numbers are in `eval/baseline.md` and `eval/runs/metrics.md`.

Claim labels: **confirmed** (source named), **inferred**, **unknown**. Line numbers marked `@9d25598` refer to the baseline commit; all others refer to this branch.

## Ranking

Defects are ordered by measured eval impact first, then by risk. The table order is the rank; F-numbers are stable labels (tests cite them), so they are not in rank order. "Fixed here" means changed in Phase 2, and each fix carries an eval delta or a blocker tag. Everything else is recorded and left to the phase named.

| # | Defect | Measured impact | Risk | Status |
|---|---|---|---|---|
| F1 | TC3 and TC4 called Public | TC false-Public 67% (6/9), 3/3 runs each; unchanged after Phase 2 | High: false-Public is the costliest error | Not fixed: Phase 3 |
| F2 | TC2 called Confidential | TC Highly Sensitive recall 0% (0/3); unchanged after Phase 2 | High | Not fixed: needs your decision, then Phase 3 |
| F9 | SSN-shaped order IDs flagged as SSN, and the model defers to the flag | After Phase 2: SYN02 and SYN10 called Highly Sensitive in 3/3 runs each (6 synthetic misses, the largest remaining synthetic error) | High | Not fixed: Phase 3 (top candidate) |
| F3 | `Unsafe` was a fourth, exclusive category | Unsafe recall 43% (9/21) → **100% (21/21)**; 9 synthetic classifications lost their sensitivity → 0 | High | **Fixed here** (schema change). Delta below |
| F16 | SYN23 (minor's identity in a safeguarding record) called Highly Sensitive | 3/3 runs after Phase 2 (baseline: 1 Highly Sensitive + 2 `Unsafe`) | Medium: definition boundary | Not fixed: Phase 3 |
| F4 | Dual verification on by default; every `/classify` fails without an OpenAI key | Not in eval (eval passed `False`) | Deploy blocker | **Fixed here**. No eval effect: deploy blocker |
| F5 | Safety short-circuit skipped classification | 0/84 in baseline (never fired) | Latent wrong label at confidence 1.0 | **Fixed here** (removed). No eval effect on this set: latent correctness blocker |
| F6 | Upload ran a second, discarded classification | Not in eval | Doubles spend per upload | **Fixed here**. No eval effect: deploy/cost blocker |
| F7 | Client filename in the save path | Not in eval | Path traversal on Windows; broken uploads on Linux | **Fixed here**. No eval effect: security blocker |
| F8 | No auth or rate limit; whole upload read into memory | Not in eval | Open upload drives API spend | Not fixed: Phase 5 |
| F10 | PII regex recall gaps | PII recall 14% (4/29) | Medium (the LLM reads the text anyway) | Not fixed: Phase 3 |
| F11 | Content-safety regex: false and missed flags | Regex unsafe recall 14% (3/21) | Low now that it is only a hint | Not fixed |
| F12 | PII detection context keeps other PII unredacted | Not in eval | Medium: stored and served as citation text | Not fixed: Phase 4/5 |
| F13 | LLM citation quotes often not on the cited page | Strict match 69% synthetic, 34% TC | Medium | Not fixed: Phase 3 |
| F14 | Legacy UI renders filename and LLM text as HTML | Not in eval | Stored XSS | Not fixed: Phase 4 replaces this UI |
| F15 | Error responses return raw exception text | Not in eval | Low (information leak) | Not fixed: Phase 5 |

## Details

### F1. TC3 and TC4 called Public (not fixed)
- **Measured:** confirmed from `eval/runs/run*.jsonl`. TC3 (internal memo) was called Public in 3/3 runs (confidence 0.60-0.72). TC4 (aviation manual) was called Public in 3/3 runs (0.82-0.85). Label stability was 100%, so this is stable and wrong.
- **Cause, inferred from the model's run-1 reasoning:**
  - TC3 was read as "academic and instructional".
  - TC4 was read as "a published, generic template distributed by a trade association".
  - The Confidential definition (`backend/prompts/prompt_library.yaml:29-42`) gives the model nothing to weigh against those signals.
- **Why not fixed here:** this is a prompt or decision-rule change, and the plan's Phase 3 candidates (fail-closed rule, definitions) are judged by the 2-document gate. Phase 2 kept the sensitivity definitions unchanged so the schema delta stays attributable.

### F2. TC2 called Confidential (not fixed; decision needed)
- **Measured:** confirmed. Confidential in 3/3 runs. The regex found only one email.
- **What TC2 contains:** confirmed by text extraction in the container, digits masked. It has no SSN, account number or card number. It has a driver's licence mentioned without a number, plus a name, address, phones, employment history, wages and criminal-history questions.
- **The conflict:** the prompt's Highly Sensitive definition is "PII like SSNs, account/credit card numbers, proprietary schematics...". Under that definition the model's answer is defensible. The golden label follows the docx test-case line ("Expected Category: Highly Sensitive"). This is the same kind of conflict as TC4, in the opposite direction.
- **Your call:** either widen the Highly Sensitive definition to cover a private individual's application data, or accept TC2 as a known definition conflict. Either way it is a Phase 3 change.

### F3. Unsafe was a fourth, exclusive category (fixed here)
- **Measured:** confirmed from `eval/runs/metrics.md`.
  - **Recall:** the shipped output flagged 9 of 21 unsafe classifications (43%).
  - **Never flagged in any run:** SYN04 (political news), SYN05 (violent news) and SYN24 (Highly Sensitive plus hate speech). The model put the sensitivity first.
  - **Sensitivity lost:** the 9 classifications returned as `Unsafe` had no sensitivity, which cost synthetic Public and Confidential recall.
  - **Definition gap:** the prompt's old `Unsafe` description left out "political news" and "exploitative", which the docx lists.
- **Cause, confirmed from code:**
  - The system prompt asked for "one of the following categories: Public, Confidential, Highly Sensitive, or Unsafe" (`prompt_library.yaml:7-8@9d25598`).
  - `classifier.py` returned one `category`.
- **Fix:**
  - **Prompt and schema:** the prompt asks for two independent labels (`prompt_library.yaml:7-8`). The `unsafe` definition is the docx line, verbatim (`prompt_library.yaml:64`; docx "Unsafe Content: In any case all content should be evaluated for Child Safety and should not include Hate speech, exploitative, violent, criminal, political news or cyber-threat content."). It is appended to the category block (`prompt_manager.py:250`), and the response format asks for `sensitivity` and `unsafe`. The sensitivity definitions are unchanged.
  - **Classifier:** `classifier.py` returns `sensitivity` and `unsafe`, rejects any other sensitivity as `failed` (`classifier.py:103-104`), and normalises `"yes"`/`"no"` (`classifier.py:20`).
  - **HITL:** `unsafe=true` triggers human review, following docx line 17: "automatically detect Unsafe content and flag for human review" (`prompt_manager.py:202`).
  - **Database:** `unsafe` columns on `documents`, `classifications` and `feedback`. `UNSAFE` is removed from the sensitivity enum.
  - **API:** `/classify`, `GET /api/documents[/{id}]` and `/api/feedback` (`corrected_unsafe`, `main.py:414`) carry both fields. The legacy UI reads them.
  - **Eval:** `eval/run_eval.py` scores `unsafe` from the new field and still reads the baseline's old shape (`pred_unsafe`, `run_eval.py:78`). `compare` prints per-document base→new results (`run_eval.py:407`). Confirmed: `report` on the baseline reproduces `eval/runs/metrics.md` with only the 4 changed label lines differing.
- **Known limitation, not changed after the measurement:** a missing or garbled `unsafe` value is read as `false` (fail-open), while an invalid sensitivity fails the classification. No such reply occurred in the 84 runs; whether `unsafe` should fail closed is a Phase 3 call.
- **Shipped signal:** `unsafe` is the LLM's decision. The regex result stays in `safety_results` as a prompt hint, a HITL trigger, and the secondary eval row.
- **Caveat for the delta:** part of any synthetic recall gain is mechanical. The baseline counted the 9 `Unsafe` rows as sensitivity misses; the new shape cannot produce that miss. The per-document `compare` table separates the two effects.
- **Eval delta:** see "Eval delta" below. Unsafe: 5 documents fixed in all 3 runs, 0 regressed. Sensitivity: 3 documents fixed (all mechanical), 1 fully regressed (SYN10) and 1 partially (SYN02), both through F9.

### F4. Dual verification on by default (fixed here)
- **Confirmed by test** (`test_classify_with_default_settings_and_no_openai_key`, red before the fix): with default settings and no OpenAI key, `/classify` logged "OpenAI client not initialized". It then returned HTTP 500 with `technical_error: 'pii_results'`.
- **Mechanism:** the endpoint calls `classify_document(path)` with no override, so `USE_DUAL_VERIFICATION=True` (`config.py:50@9d25598`) sent every request to the GPT-3.5 verifier. The eval passed `use_dual_verification=False`, so the measured path was not the shipped path.
- **Fix:** default `False` (`config.py:50`), matching PLAN call 3. Second-pass verification stays a Phase 3 candidate.
- **`.env.example` too:** it set `USE_DUAL_VERIFICATION=True` and the retired `PRIMARY_LLM_MODEL=claude-3-haiku-20240307` (lines 22 and 24 @9d25598), so copying it to `.env` undid both this fix and the Phase 1b port. Both lines now match the code defaults. Separately, its comma-separated `ALLOWED_ORIGINS` made `config.py` raise `SettingsError` at import (confirmed in the container). pydantic-settings parses list fields as JSON, so the line is now a JSON list (your fix, ported). The same applied to `ALLOWED_EXTENSIONS`: a JSON line was added, and the old comma-separated line further down, which overrode it and still crashed at import, was removed. Verified: the whole `.env.example`, mounted as `.env`, loads, and pytest passes against it. `SECONDARY_LLM_MODEL` is now `claude-sonnet-5-5`, so a future second pass needs no OpenAI key; it stays off.
- **Also fixed:** the endpoint now raises on a failed classification (`main.py:260`) instead of crashing on a missing key. The existing error handler categorises it.
- **Tag:** no eval effect: deploy blocker.

### F5. Safety short-circuit (removed)
- **Measured:** confirmed. All 84 baseline records have status `completed`; none was `blocked`. SYN12's regex flag was `cyber_threat`, which is medium severity, and the short-circuit only blocked critical or high. So `eval/baseline.md` is wrong where it says SYN12 was "blocked by the regex safety check": the LLM chose `Unsafe` for SYN12 itself. `baseline.md` is left as written; this entry is the correction.
- **Latent defect:** confirmed from code at `classifier.py:87-96@9d25598`. Any critical or high keyword returned `Unsafe` at confidence 1.0 with no sensitivity and no LLM call. One such keyword is the bare word "minor" (see F11).
- **Fix:** removed. Regex flags now reach the LLM as context and trigger HITL (`classifier.py:91`). Test: `test_critical_safety_hit_still_classified`.
- **Tag:** no eval effect on this set: latent correctness blocker.

### F6. Upload ran a second, discarded classification (fixed here)
- **Confirmed by test** (`test_upload_does_not_classify`, red before the fix): one upload called the classifier once. The background task (`main.py:334-357@9d25598`) never saved the result; its save logic is the comment `# ... (similar code to above)`.
- **Double spend:** the UI then calls `/classify` itself (`frontend/public/index.html:533-534`), so each upload paid for two LLM calls (inferred from these two confirmed facts).
- **Session use:** the task used the request-scoped session after the response. Whether that session is still valid there is unknown: fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield does not state the order, and it no longer matters.
- **Fix:** the task is removed. Upload only stores the file, and `/classify` is the single path that classifies and saves. A background or batch mode is Phase 4's call.
- **Tag:** no eval effect: deploy/cost blocker.

### F7. Client filename in the save path (fixed here)
Code at `@9d25598`: `safe_filename = f"{timestamp}_{file.filename}"` (`main.py:123`), then `os.path.join(UPLOAD_DIR, ...)`. Starlette passes the multipart filename through unchanged (confirmed: the Linux error message showed `uploads/20261113_225648_../../escape.pdf`).

- **Linux container** (the deploy target), confirmed by `test_upload_keeps_client_filename_out_of_save_path`, 4 cases:
  - `../../escape.pdf`, `/tmp/abs_escape.pdf` and `a/../../../escape.pdf` returned HTTP 500 `ENOENT`. Nothing escaped, because the kernel needs the fake directory `<ts>_..` to exist. Any filename containing `/` therefore failed to upload.
  - `..\..\escape.pdf` was stored under that literal name.
- **Windows**, confirmed by replaying the same three lines outside the app: `x/../../escape_fs.pdf` was written to the parent of `uploads/`. Windows collapses `..` lexically, so the fake directory need not exist, and more `../` reaches further.
- **Also from the code** (inferred): two uploads with the same name in the same second overwrote each other.
- **Fix:** the stored name is `uuid4().hex` plus the allow-listed extension (`main.py:118-119`). The client name is kept only in `documents.original_filename`. All 4 cases now return 200, the file is saved inside `UPLOAD_DIR`, and nothing is written outside.
- **Tag:** no eval effect: security blocker.

### F8. No auth or rate limit (recorded; Phase 5)
- Confirmed from `main.py`: upload, classify and feedback have no authentication and no limits. Upload reads the whole body into memory before the size check (`main.py:100`), up to `MAX_FILE_SIZE_MB=50`.
- PLAN Phase 5 owns the per-IP limit, global daily cap, file-size and page caps, file deletion after classification, and the Console spend cap. Nothing was added here.

### F9. SSN-shaped order IDs (recorded; Phase 3, top candidate)
- **Measured, baseline:** confirmed. All 5 SSN false positives are decoys, and SYN02 (Public FAQ) was called Highly Sensitive in 2/3 runs; the model's reasoning cites "the automated PII scan flagged SSN-type identifiers".
- **Measured, after Phase 2:** confirmed from `eval/runs_phase2/`. SYN02 is now Highly Sensitive in 3/3 runs, and SYN10 (Confidential runbook with SSN-shaped lookups) went from Confidential 3/3 to Highly Sensitive 3/3. SYN10's run-1 reasoning: the runbook "on its own fits the Confidential category", but "the PII scanner, however, detected SSN-format values with high severity".
- **Why it got worse:** unknown. The two-field prompt is the only change on this path. One run set cannot say whether the model now weighs the "PII Detected / Severity: high" prompt block more, or whether this is variance that happened to be stable.
- **Cause, confirmed from code:** `_validate_ssn` checks only format, and its result is put in the prompt as "Severity: high" (`prompt_manager.py`, PII block). Pinned by `test_pii_ignores_ssn_shaped_order_id` (xfail, strict).
- **Phase 3 candidates:** model-extracted PII, or not sending the regex severity to the model.

### F16. SYN23 called Highly Sensitive (recorded; Phase 3)
- **Measured:** confirmed. Highly Sensitive in 3/3 runs after Phase 2, with `unsafe` correct 3/3. In the baseline it was Highly Sensitive once and `Unsafe` twice, so the baseline also had it wrong 3/3.
- **Cause, inferred from the reasoning:** the record "identifies a minor by full name, year group, and age". The golden label follows "customer details (names, addresses)" → Confidential. This is a definition boundary (a minor's identity in a child-protection record), like F2.

### F10. PII regex recall gaps (recorded; Phase 3)
- **Measured:** confirmed. CREDIT_CARD 0/3: the manifest numbers are spaced, and the regex needs contiguous digits (pinned by `test_pii_detects_spaced_card_number`, xfail strict). PHONE 0/1, ACCOUNT_NUMBER 0/1 and DATE_OF_BIRTH 0/1. PERSON and ADDRESS have no detector.
- **Effect on labels:** inferred to be small on this set, because synthetic Highly Sensitive recall is 96% (the LLM reads the text). The Phase 3 candidate is model-extracted PII.

### F11. Content-safety regex: false and missed flags (recorded)
Both behaviours are confirmed from `content_safety.py`:
- **False flags:** the bare keyword "minor" raises a critical `child_safety` flag (line 19). "We made minor changes to the schedule" is flagged (pinned by `test_content_safety_ignores_minor_changes`, xfail strict).
- **Missed flags:** a single "safe context" word anywhere on the page ("training", "education", "news report"…) lowers every flag on that page to 0.4, below the 0.5 threshold (lines 79 and 125).

Before F5 was fixed, the false-flag case meant a wrong label. Now it only adds a HITL review.

### F12. PII context leak (recorded; Phase 4/5)
- **Confirmed by test:** `test_pii_context_redacts_neighbouring_pii` (xfail, strict).
- **Mechanism:** `_redact_context` (`pii_detector.py:97`) redacts only the detection's own value. A nearby SSN stays readable in an email detection's 100-character context.
- **Exposure:** that context is stored as `citation_evidence.evidence_text` and served by `GET /api/documents/{id}`. Inferred: the uploader can already see the document, so the risk is in logs, exports or a shared queue, which Phase 4/5 decide.

### F13. Citation quotes (recorded; Phase 3)
- **Measured:** confirmed. The quote is on the cited page for 69% (191/277) of synthetic citations and 34% (32/95) of TC citations under the strict check.
- **Supplementary check:** inferred from `eval/cite_check.py`. Most mismatches are punctuation differences; the rest are paraphrased or stitched quotes.
- **Phase 3:** the mandatory candidate is native PDF input with citations.

### F14. Legacy UI XSS (recorded; Phase 4)
- Confirmed from code: `frontend/public/index.html` builds result and list markup with `innerHTML`, and inserts `doc.filename` (line 763, client-controlled) and the LLM's summary and reasoning unescaped.
- Phase 4 replaces this UI. It must not be deployed as is. Phase 2 changed only the field names it reads (`sensitivity`, `unsafe`); that change was not checked in a browser.

### F15. Raw exception text in responses (recorded; Phase 5)
- Confirmed from code: the `/classify` error handler returns `technical_error: str(e)` (`main.py:322`), and upload and feedback put `str(e)` in `detail`.

## Adjacent issues (listed, not fixed)
- **Existing local databases:** a local `regulatory_classifier.db` lacks the new `unsafe` columns. `create_all` does not migrate, and Alembic is unused, so delete the file. The Render instance starts empty anyway (PLAN evidence).
- **Feedback validation:** `/api/feedback` with an invalid `corrected_category` (including the old "Unsafe") returns 500, not 400.
- **Booleans in Text columns:** `classifications.content_safety_passed`, `pii_detected` and `is_verified` are `Text` columns that hold booleans.
- **Missing HITL trigger:** `multiple_categories_detected` is in `prompt_library.yaml` but is never implemented in `check_hitl_triggers`.
- **Unused setting:** `REDIS_URL` (`config.py:39`) is never read.
- **Deprecations:** `datetime.utcnow()` warnings (87 in the pytest run).
- **Dual verification not re-measured:** its prompt and agreement score were updated for the two fields, but the path was not run (no OpenAI key; off by default).
- **Stale docs:** `README.md:356` still shows `USE_DUAL_VERIFICATION=True`, and `README.md:56` claims "HITL Reduction: 60-70% through dual verification" with no measurement behind it. `docs/ARCHITECTURE.md:319-333` describes Celery/Redis and FastAPI BackgroundTasks, all now gone.
- **Duplicate PDF libraries:** both `PyPDF2` (backend) and `pypdf` (`eval/make_synthetic.py --check`) are imported, so neither pin is unused. Merging them means porting `document_processor.py` to `pypdf`.

## Tests
`test_system.py` was a print-only script; it is now a pytest suite. It needs no API key: the Anthropic call and, for API tests, document processing are faked.

Confirmed results, run in the `docclf-eval` image:
- **Before the fixes:** 20 failed, 3 passed, 3 xfailed. The red tests covered F3-F7 and the schema.
- **After the fixes:** 23 passed, 4 xfailed.

The 4 xfails are strict and pin F9, F10, F11 and F12, so fixing one of them flips its test red. The same result holds on the trimmed `docclf-eval:phase2` image, with and without an empty file masked over `.env`. Mask it: `config.py` reads `.env`, and a real one can override the defaults the tests check.

```bash
docker build -t docclf-eval:phase2 .
# <empty-file> is any empty file; it hides a real .env from the container
docker run --rm -v "$PWD":/app -v <empty-file>:/app/.env:ro -w /app docclf-eval:phase2 python -m pytest -q test_system.py
```

## Reproduce the Phase 2 eval

```bash
docker run --rm -e ANTHROPIC_API_KEY -v "$PWD":/app -v <empty-file>:/app/.env:ro -w /app docclf-eval:phase2 \
  python eval/run_eval.py run --runs 3 --dir eval/runs_phase2_repro
docker run --rm -v "$PWD":/app -w /app docclf-eval:phase2 \
  python eval/run_eval.py compare --base eval/runs --dir eval/runs_phase2_repro
```

`eval/runs/` (the baseline) is reproducible only at commit `9d25598`. On this branch the classifier emits the two-field shape.

## Eval delta (3-run protocol, same documents, PDF-set hash `54515af65bd01e66`)

Run on 2026-11-13 with everything above in place: image `docclf-eval:phase2` (trimmed dependencies), `claude-haiku-5-5`, `anthropic==1.17.0`, dual verification off. 84/84 classifications completed, 0 failures.
- **Inputs:** `eval/runs_phase2/` (`metrics.md`, per-document `compare.md`) against `eval/runs/`.
- **Estimate:** `count_tokens` gave 56,164 input tokens per run (confirmed, `eval/runs_phase2/estimate.json`). At the 1,500-token output assumption that is about $0.080 for 3 runs (inferred: the script's own formula), under the approved $0.20 cap.
- **Actual spend:** $0.0839 ($0.0239 TC + $0.0600 synthetic; confirmed, `metrics.md`).

All numbers below are confirmed from the two `metrics.md` files and `compare.md`.

### TC1-TC4 (4 docs × 3 runs)

| Metric | Baseline | Phase 2 | Delta |
|---|---|---|---|
| Recall Public / Confidential / Highly Sensitive | 100% / 0% / 0% | 100% / 0% / 0% | none |
| False-Public rate | 67% (6/9) | 67% (6/9) | none |
| Docs correct per run | 1/4, 1/4, 1/4 | 1/4, 1/4, 1/4 | none |
| Unsafe false alarms | 0/12 | 0/12 | none (no positives, so precision and recall are undefined) |
| Citation quote on page (strict) | 34% (32/95) | 36% (34/95) | +2 pts |
| Classifications with ≥1 valid citation | 83% (10/12) | 100% (12/12) | +17 pts |
| Cost per classification (mean) | $0.00190 | $0.00199 | +5% |
| Latency total, median / p90 | 12.5 s / 20.4 s | 14.8 s / 28.9 s | +2.3 s / +8.4 s |
| Output tokens (mean) | 2,202 | 2,368 | +8% |

No TC regression, and no TC gain. F1 and F2 are untouched by design.

### Synthetic (24 docs × 3 runs)

| Metric | Baseline | Phase 2 | Delta |
|---|---|---|---|
| **Unsafe recall** | 43% (9/21) | **100% (21/21)** | +57 pts |
| **Unsafe precision** | 100% (9/9) | **100% (21/21)** | held, on 21 predictions instead of 9 |
| Recall Public | 79% (19/24) | 88% (21/24) | +9 pts |
| Recall Confidential | 75% (18/24) | 75% (18/24) | 0 (+SYN12, −SYN10) |
| Recall Highly Sensitive | 96% (23/24) | 100% (24/24) | +4 pts |
| False-Public rate | 0% (0/48) | 0% (0/48) | none |
| Sensitivity lost to `Unsafe` | 9 | 0 | −9 (mechanical) |
| Docs correct per run | 20, 21, 19 | 21, 21, 21 | +1 mean |
| Label stability | 88% (21/24) | 100% (24/24) | +12 pts |
| Citation quote on page (strict) | 69% (191/277) | 71% (205/287) | +2 pts |
| Cost per classification (mean) | $0.00077 | $0.00083 | +8% |
| Latency total, median / p90 | 6.2 s / 9.0 s | 7.1 s / 9.1 s | +0.8 s / +0.1 s |
| PII regex (precision / recall) | 31% / 14% | 31% / 14% | identical (detector unchanged) |

### Per document (`eval/runs_phase2/compare.md`; "fixed" = wrong in at least one baseline run, right in all 3 new runs)
- **Unsafe fixed (5 docs, all 3 runs):** SYN04 (political news), SYN05 (violent news), SYN21 (criminal), SYN23 (child safety), SYN24 (hate speech). 0 regressed.
- **Sensitivity fixed (3 docs):** SYN12, SYN21, SYN22. All three were `Unsafe` rows in the baseline, so these gains are **mechanical**: the old output shape could not carry a sensitivity for them.
- **Sensitivity regressed:** SYN10 (3/3 → 0/3) and SYN02 (1/3 → 0/3), both through F9.
- **Net non-mechanical sensitivity effect:** −4 classifications (SYN10 −3, SYN02 −1).

### Reading
- **Unsafe:** the change clears the PLAN gate (at least 2 documents fixed in all 3 runs, no TC regression), with 5 documents. It is two changes measured together: the two-field split, and the docx-verbatim `unsafe` definition, which adds "political news" and "exploitative". One rerun cannot separate them; SYN04 (political news) is the case most likely helped by the definition (inferred). Unsafe precision and recall are now measurable and both 100% on the synthetic set. The circularity caveat still applies: Claude wrote these documents and is grading them.
- **Sensitivity:** the synthetic gains are mechanical, and the one real behavioural change is negative (F9). F9 now outranks every remaining synthetic error.
- **Label stability:** this measures sensitivity only. Part of the 88% → 100% gain is mechanical (SYN21 and SYN23 used to flip between Highly Sensitive and `Unsafe`), and SYN02 is now stable and wrong.
- **Cost and latency:** cost rose 5-8%. Input tokens rose (synthetic mean 947 → 1,001, TC 7,984 → 8,038) because of the longer prompt (`count_tokens`: 54,652 → 56,164 per run, +3%). Output tokens rose more (1,355 → 1,467 and 2,202 → 2,368), inferred to be because the model now reasons about two labels. Latency rose 0.8 s median on synthetic and 2.3 s on TC. TC p90 rose 8.4 s on 12 classifications. Whether that is run-to-run noise is unknown from one run set.
