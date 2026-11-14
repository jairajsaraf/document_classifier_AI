## Metrics

Run metadata: `{"model": "claude-haiku-5-5", "sdk": "1.17.0", "python": "3.12.16", "pdf_set_hash": "54515af65bd01e66", "dual_verification": false, "runs": 3, "arm": {"input_mode": "pdf_structured", "pii_hints": true, "fail_closed": false, "wide_hs": true, "max_tokens": 8192}, "started": "2026-11-14 04:01:52"}`

### TC1-TC4 (datathon test cases) (4 docs x 3 runs = 12 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = category Unsafe replaced the sensitivity (baseline output shape only), `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 3 | 0 | 0 | 0 | 0 | 100% (3/3) |
| Confidential | 6 | 0 | 0 | 0 | 0 | 0% (0/6) |
| Highly Sensitive | 0 | 0 | 3 | 0 | 0 | 100% (3/3) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 67% (6/9)
- Highly Sensitive predicted Public: 0% (0/3)
- Predicted Unsafe (sensitivity not measurable for these): 0; failed or unparsed: 0
- Docs with the golden sensitivity, per run: run1: 2/4, run2: 2/4, run3: 2/4

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| shipped output (`unsafe` field; baseline: category == Unsafe) | n/a | n/a | the LLM's decision; positives in group: 0 |
| regex safety flag raised | n/a | n/a | secondary: any flag, even if not blocked; positives in group: 0 |

Label stability: 100% (4/4) of docs got the same category in all 3 runs

Citation validity (LLM-produced citations only; code-generated PII/safety citations [3] carry redacted context and are not graded):

- LLM citations: 44; cited page exists: 100% (44/44); quote found on that page: 66% (29/44)
- Completed classifications with at least one valid citation: 83% (10/12)
- of which extracted by the Citations API (valid pointers by construction): 0; their quote also matches this pipeline's page text: n/a
- image-region citations (described, not checkable): 6; evidence lines the API attached no citation to: 0
- Completed classifications with no page citation at all: 0% (0/12)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00264, max $0.00518, total $0.0317
- total seconds: median 13.24, p90 38.03, mean 16.48
- API seconds: median 6.94, p90 9.48, mean 6.87
- input tokens mean 20879, output tokens mean 1112
- stop reasons: {'end_turn': 12}

### Synthetic (24 docs) (24 docs x 3 runs = 72 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = category Unsafe replaced the sensitivity (baseline output shape only), `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 23 | 1 | 0 | 0 | 0 | 96% (23/24) |
| Confidential | 0 | 21 | 0 | 0 | 0 | 100% (21/21) |
| Highly Sensitive | 0 | 0 | 27 | 0 | 0 | 100% (27/27) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 0% (0/48)
- Highly Sensitive predicted Public: 0% (0/27)
- Predicted Unsafe (sensitivity not measurable for these): 0; failed or unparsed: 0
- Docs with the golden sensitivity, per run: run1: 23/24, run2: 24/24, run3: 24/24

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| shipped output (`unsafe` field; baseline: category == Unsafe) | 100% (21/21) | 100% (21/21) | the LLM's decision; positives in group: 7 |
| regex safety flag raised | 100% (3/3) | 14% (3/21) | secondary: any flag, even if not blocked; positives in group: 7 |

Label stability: 96% (23/24) of docs got the same category in all 3 runs; unstable: SYN02 [('Confidential', 1), ('Public', 2)]

Citation validity (LLM-produced citations only; code-generated PII/safety citations [42] carry redacted context and are not graded):

- LLM citations: 253; cited page exists: 100% (253/253); quote found on that page: 100% (253/253)
- Completed classifications with at least one valid citation: 100% (72/72)
- of which extracted by the Citations API (valid pointers by construction): 0; their quote also matches this pipeline's page text: n/a
- image-region citations (described, not checkable): 4; evidence lines the API attached no citation to: 0
- Completed classifications with no page citation at all: 0% (0/72)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00100, max $0.00150, total $0.0722
- total seconds: median 5.27, p90 6.70, mean 5.37
- API seconds: median 4.78, p90 6.40, mean 4.95
- input tokens mean 5373, output tokens mean 932
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
