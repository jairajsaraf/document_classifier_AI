# Baseline eval (Phase 1)

Measured 2026-11-13 on branch `plan/eval-and-deploy`. Everything below was run: 3 runs, 28 scored documents (TC1-TC4 plus 24 synthetic), 84 classifications, 0 failures. Claim labels: **confirmed** (read from `eval/runs/*.jsonl`), **inferred**, **unknown**.

## What was measured

| Item | Value |
|---|---|
| Model | `claude-haiku-5-5`, default effort and thinking (nothing set), `max_tokens` 4096 (confirmed: `eval/runs/meta.json`, `backend/config.py`) |
| SDK | `anthropic==1.17.0` on Python 3.12.16, Docker image `python:3.12-slim` + tesseract 5.5.0 |
| Dual verification | off (`use_dual_verification=False` passed by `run_eval.py`) |
| Documents | `scored=yes` rows of `eval/golden.csv`; TC5 excluded as decided. Synthetic PDF-set hash `54515af65bd01e66`, identical to the hash in `eval/README.md` |
| Actual spend | $0.078 for all 84 calls (estimate was $0.04-$0.19, `count_tokens` input 54,652 tokens per run) |

## The baseline diff

Only the changes the plan allows, plus two dependency bumps that the SDK upgrade forced (user-approved):
- `backend/config.py`: default model `claude-haiku-5-5`.
- `backend/services/classifier.py`: `temperature` dropped from the Anthropic call; text read by block type.
- `backend/requirements.txt`: `anthropic` 0.7.8 -> 1.17.0. `anthropic` 1.x needs `anyio>=4.1`, while `fastapi==0.104.1` and `openai==1.3.7` need `anyio<4`, so `fastapi` -> 0.109.2 and `openai` -> 1.12.0 (smallest versions pip's resolver accepted). The web app and OpenAI path were not tested against these (only `/health`, `/`, `/api` were).

```diff
diff --git a/backend/config.py b/backend/config.py
index f7ef20f..7539f51 100644
--- a/backend/config.py
+++ b/backend/config.py
@@ -40,7 +40,7 @@ class Settings(BaseSettings):
 
     # LLM Configuration
     PRIMARY_LLM_MODEL: str = Field(
-        default="claude-3-haiku-20240307",
+        default="claude-haiku-5-5",
         env="PRIMARY_LLM_MODEL"
     )
     SECONDARY_LLM_MODEL: str = Field(
diff --git a/backend/requirements.txt b/backend/requirements.txt
index 459f1d6..dd17b12 100644
--- a/backend/requirements.txt
+++ b/backend/requirements.txt
@@ -1,5 +1,5 @@
 # Core Framework
-fastapi==0.104.1
+fastapi==0.109.2
 uvicorn[standard]==0.24.0
 python-multipart==0.0.6
 pydantic==2.5.0
@@ -23,8 +23,8 @@ opencv-python==4.8.1.78
 numpy==1.26.2
 
 # LLM Integration (using Anthropic Claude for lightweight/cost-effective processing)
-anthropic==0.7.8
-openai==1.3.7
+anthropic==1.17.0
+openai==1.12.0
 tiktoken==0.5.2
 
 # Content Safety & PII Detection
diff --git a/backend/services/classifier.py b/backend/services/classifier.py
index c6ca3dc..059ca55 100644
--- a/backend/services/classifier.py
+++ b/backend/services/classifier.py
@@ -259,12 +259,12 @@ class DocumentClassifier:
             message = self.anthropic_client.messages.create(
                 model=model,
                 max_tokens=settings.MAX_TOKENS,
-                temperature=settings.TEMPERATURE,
                 messages=[
                     {"role": "user", "content": prompt}
                 ]
             )
-            return message.content[0].text
+            # Haiku 5.5 may lead with a thinking block: read text blocks by type
+            return "".join(b.text for b in message.content if b.type == "text")
         except Exception as e:
             logger.error(f"Anthropic API call failed: {e}")
             raise
```

## Headline numbers (pooled over 3 runs)

| Metric | TC1-TC4 (4 docs) | Synthetic (24 docs) |
|---|---|---|
| Recall: Public | 100% (3/3) | 79% (19/24) |
| Recall: Confidential | **0% (0/6)** | 75% (18/24) |
| Recall: Highly Sensitive | **0% (0/3)** | 96% (23/24) |
| False-Public rate (Confidential or Highly Sensitive called Public) | **67% (6/9)** | 0% (0/48) |
| Unsafe precision / recall | n/a (no positives) | 100% (9/9) / **43% (9/21)** |
| Label stability, same category in all 3 runs | 100% (4/4) | 88% (21/24) |
| Citations: cited page exists | 99% (94/95) | 100% (277/277) |
| Citations: quote found on page, strict | 34% (32/95) | 69% (191/277) |
| Cost per classification (mean) | $0.0019 | $0.00077 |
| Latency per classification, total (median / p90) | 12.5 s / 20.4 s | 6.2 s / 9.0 s |
| PII (regex detector, per entity below) | not scored (no manifest) | precision 31% (4/13), recall 14% (4/29) |

Recall counts a document the classifier returned as `Unsafe` as a miss for its sensitivity class, because the shipped output cannot carry both fields (see "Not measurable").

## What the numbers say

All confirmed from `eval/runs/` unless marked.

- **The test cases fail where it matters.** TC3 (internal memo, Confidential) and TC4 (aviation manual, Confidential) were called Public in all 3 runs, with confidence 0.60-0.72 and 0.82-0.85. TC2 (filled-in employment application, Highly Sensitive) was called Confidential in all 3 runs. TC1 (Public) was right every time. Stable and wrong: 100% label stability here is not a good sign.
- **Synthetic is better but not clean.** Zero false-Public. Errors: SYN02 (Public FAQ with SSN-shaped order IDs) was called Highly Sensitive in 2 of 3 runs; SYN23 (Confidential, child-safety) varied between Highly Sensitive and Unsafe; SYN21 (Highly Sensitive, criminal) was called Unsafe in 1 run.
- **Unsafe recall is 43%.** Caught: SYN12 (3/3, by the regex checker), SYN22 (3/3), SYN23 (2/3), SYN21 (1/3). Missed in all 3 runs: SYN04 (political news), SYN05 (violent news), SYN24 (hate speech). Only SYN12 was blocked by the regex safety check; the other six Unsafe calls were the LLM choosing the category. Precision is 100%, but on 9 predictions.
- **PII detector (regex, not the LLM).** SSN recall is 100% (4/4) but precision 44%: all 5 false positives are decoys (order IDs shaped like SSNs). CREDIT_CARD 0/3 (the detector needs contiguous digits; the manifest numbers are spaced, e.g. `4111 1111 1111 1111`), PHONE 0/1, ACCOUNT_NUMBER 0/1, DATE_OF_BIRTH 0/1, PERSON 0/10 and ADDRESS 0/9 (no detector exists for these). All 4 EMAIL detections are business-contact decoys. The detector's output is identical across runs.
- **Citations.** The cited page almost always exists. The quote is on that page for 69% of synthetic and 34% of test-case citations under the strict check (case- and whitespace-insensitive substring; `...` splits a quote into segments). The strict check understates it: on text-layer pages in run 1, a punctuation-insensitive check matches 105 of 118 citations (89%) against 73 strict; on TC pages, 22 of 29 against 9 (`python eval/cite_check.py`, inferred supplementary). The remaining mismatches are paraphrased or stitched quotes. Image-only pages are not in that supplementary check.
- **Cost and latency.** Prices from the claude-api skill (confirmed): $0.10 / $0.50 per million input / output tokens. Mean output is 1,355 tokens (synthetic) and 2,202 (TC), which includes thinking, since Haiku 5.5 thinks by default (inferred from the token counts; thinking text is omitted by default). All 84 calls ended with `end_turn`; none hit the 4,096 cap.

## Not measurable with the current output shape

- **Sensitivity for documents returned as `Unsafe`** (9 synthetic classifications): the regex short-circuit and the LLM `Unsafe` category replace the sensitivity label. TC5's Confidential-and-Unsafe case is exactly this, and is unscored anyway.
- **Unsafe on TC1-TC4:** no unsafe positives, so precision and recall are undefined; no false alarms either (0 of 12).
- **PII on TC1-TC4:** no manifest exists. Entity-level PII scores are synthetic only.
- **LLM-based PII detection:** the classifier has none; the PII figures measure the regex detector only.
- **Regions:** citations carry page and excerpt only, so the docx's "cite the region with the serial" (TC4) cannot be scored. Phase 3 item.
- **Confidence calibration** was not computed.

## Caveats

- **Small sample.** 8 documents per class means one document moves class recall by 12.5 points; 3 runs of the same documents are not 3 independent samples. Use the PLAN gate (at least 2 documents fixed, in all 3 runs, no TC regression) for any claimed win.
- **Circularity.** The synthetic documents were written by Claude and are graded against labels derived from quoted docx rules; the test cases are the independent check, and they are the worst numbers above.
- **Pillow.** The PDFs were generated in the container (Pillow 10.1.0, per `requirements.txt`); the set hash matched the README's value.
- **OCR.** SYN19 (image-only page) was flagged low legibility (0.434) but still classified Highly Sensitive in all runs.

## Pointers for Phase 2 (not fixed here)

False-Public on TC3/TC4, the safety short-circuit hiding sensitivity, the look-alike SSN false positives flipping SYN02, and the regex gaps above. `docs/FAILURES.md` should rank them.

## Reproduce

```bash
docker build -t docclf-eval .
# key passed through the environment; an empty file hides .env so the defaults apply
docker run --rm -e ANTHROPIC_API_KEY -v "$PWD":/app -v <empty-file>:/app/.env:ro -w /app docclf-eval \
  python eval/run_eval.py run --runs 3
```


---

# Full generated metrics (`python eval/run_eval.py report`)

## Metrics (raw)

Run metadata: `{"model": "claude-haiku-5-5", "sdk": "1.17.0", "python": "3.12.16", "pdf_set_hash": "54515af65bd01e66", "dual_verification": false, "runs": 3, "started": "2026-11-13 22:12:27"}`

### TC1-TC4 (datathon test cases) (4 docs x 3 runs = 12 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = the classifier returned category Unsafe, `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 3 | 0 | 0 | 0 | 0 | 100% (3/3) |
| Confidential | 6 | 0 | 0 | 0 | 0 | 0% (0/6) |
| Highly Sensitive | 0 | 3 | 0 | 0 | 0 | 0% (0/3) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 67% (6/9)
- Highly Sensitive predicted Public: 0% (0/3)
- Predicted Unsafe (sensitivity not measurable for these): 0; failed or unparsed: 0
- Docs with the golden sensitivity, per run: run1: 1/4, run2: 1/4, run3: 1/4

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| category == Unsafe (shipped output) | n/a | n/a | regex short-circuit or LLM category; positives in group: 0 |
| regex safety flag raised | n/a | n/a | secondary: any flag, even if not blocked; positives in group: 0 |

Label stability: 100% (4/4) of docs got the same category in all 3 runs

Citation validity (LLM-produced citations only; code-generated PII/safety citations [3] carry redacted context and are not graded):

- LLM citations: 95; cited page exists: 99% (94/95); quote found on that page: 34% (32/95)
- Completed classifications with at least one valid citation: 83% (10/12)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00190, max $0.00304, total $0.0228
- total seconds: median 12.50, p90 20.43, mean 13.94
- API seconds: median 9.67, p90 10.76, mean 9.55
- input tokens mean 7984, output tokens mean 2202
- stop reasons: {'end_turn': 12}

### Synthetic (24 docs) (24 docs x 3 runs = 72 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = the classifier returned category Unsafe, `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 19 | 0 | 2 | 3 | 0 | 79% (19/24) |
| Confidential | 0 | 18 | 1 | 5 | 0 | 75% (18/24) |
| Highly Sensitive | 0 | 0 | 23 | 1 | 0 | 96% (23/24) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 0% (0/48)
- Highly Sensitive predicted Public: 0% (0/24)
- Predicted Unsafe (sensitivity not measurable for these): 9; failed or unparsed: 0
- Docs with the golden sensitivity, per run: run1: 20/24, run2: 21/24, run3: 19/24

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| category == Unsafe (shipped output) | 100% (9/9) | 43% (9/21) | regex short-circuit or LLM category; positives in group: 7 |
| regex safety flag raised | 100% (3/3) | 14% (3/21) | secondary: any flag, even if not blocked; positives in group: 7 |

Label stability: 88% (21/24) of docs got the same category in all 3 runs; unstable: SYN02 [('Highly Sensitive', 2), ('Public', 1)], SYN21 [('Highly Sensitive', 2), ('Unsafe', 1)], SYN23 [('Highly Sensitive', 1), ('Unsafe', 2)]

Citation validity (LLM-produced citations only; code-generated PII/safety citations [42] carry redacted context and are not graded):

- LLM citations: 277; cited page exists: 100% (277/277); quote found on that page: 69% (191/277)
- Completed classifications with at least one valid citation: 81% (58/72)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00077, max $0.00115, total $0.0556
- total seconds: median 6.22, p90 9.04, mean 6.58
- API seconds: median 5.96, p90 8.89, mean 6.32
- input tokens mean 947, output tokens mean 1355
- stop reasons: {'end_turn': 72}

### PII detection (synthetic only; the regex detector's output, run 1)

A detection is correct when type, normalised value and page all match a manifest row with `is_pii=yes`. FP = any other detection of that type; `decoy` = it matched an `is_pii=no` row.

| entity type | planted | TP | FN | FP | of which decoy | precision | recall |
|---|---|---|---|---|---|---|---|
| ACCOUNT_NUMBER | 1 | 0 | 1 | 0 | 0 | n/a | 0% (0/1) |
| ADDRESS (no detector exists: recall 0 by construction) | 9 | 0 | 9 | 0 | 0 | n/a | 0% (0/9) |
| CREDIT_CARD | 3 | 0 | 3 | 0 | 0 | n/a | 0% (0/3) |
| DATE_OF_BIRTH | 1 | 0 | 1 | 0 | 0 | n/a | 0% (0/1) |
| EMAIL | 0 | 0 | 0 | 4 | 4 | 0% (0/4) | n/a |
| ORDER_ID | 0 | 0 | 0 | 0 | 0 | n/a | n/a |
| PERSON (no detector exists: recall 0 by construction) | 10 | 0 | 10 | 0 | 0 | n/a | 0% (0/10) |
| PHONE | 1 | 0 | 1 | 0 | 0 | n/a | 0% (0/1) |
| SSN | 4 | 4 | 0 | 5 | 5 | 44% (4/9) | 100% (4/4) |
| **all** | 29 | 4 | 25 | 9 | | 31% (4/13) | 14% (4/29) |

Detections identical across runs: yes. DRIVERS_LICENSE/PASSPORT detections have no manifest type and appear as FP rows if present.

### Failures

none
