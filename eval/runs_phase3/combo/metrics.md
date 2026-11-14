## Metrics

Run metadata: `{"model": "claude-haiku-5-5", "sdk": "1.17.0", "python": "3.12.16", "pdf_set_hash": "54515af65bd01e66", "dual_verification": false, "runs": 3, "arm": {"input_mode": "text", "pii_hints": false, "fail_closed": true, "wide_hs": true, "max_tokens": 4096}, "started": "2026-11-14 01:28:47"}`

### TC1-TC4 (datathon test cases) (4 docs x 3 runs = 12 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = category Unsafe replaced the sensitivity (baseline output shape only), `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 3 | 0 | 0 | 0 | 0 | 100% (3/3) |
| Confidential | 0 | 6 | 0 | 0 | 0 | 100% (6/6) |
| Highly Sensitive | 0 | 0 | 3 | 0 | 0 | 100% (3/3) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 0% (0/9)
- Highly Sensitive predicted Public: 0% (0/3)
- Predicted Unsafe (sensitivity not measurable for these): 0; failed or unparsed: 0
- Docs with the golden sensitivity, per run: run1: 4/4, run2: 4/4, run3: 4/4

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| shipped output (`unsafe` field; baseline: category == Unsafe) | n/a | n/a | the LLM's decision; positives in group: 0 |
| regex safety flag raised | n/a | n/a | secondary: any flag, even if not blocked; positives in group: 0 |

Label stability: 100% (4/4) of docs got the same category in all 3 runs

Citation validity (LLM-produced citations only; code-generated PII/safety citations [3] carry redacted context and are not graded):

- LLM citations: 91; cited page exists: 100% (91/91); quote found on that page: 31% (28/91)
- Completed classifications with at least one valid citation: 92% (11/12)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00201, max $0.00298, total $0.0242
- total seconds: median 14.69, p90 28.47, mean 17.76
- API seconds: median 10.50, p90 11.68, mean 10.18
- input tokens mean 8327, output tokens mean 2362
- stop reasons: {'end_turn': 12}

### Synthetic (24 docs) (24 docs x 3 runs = 72 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = category Unsafe replaced the sensitivity (baseline output shape only), `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 16 | 8 | 0 | 0 | 0 | 67% (16/24) |
| Confidential | 0 | 20 | 1 | 0 | 0 | 95% (20/21) |
| Highly Sensitive | 0 | 0 | 27 | 0 | 0 | 100% (27/27) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 0% (0/48)
- Highly Sensitive predicted Public: 0% (0/27)
- Predicted Unsafe (sensitivity not measurable for these): 0; failed or unparsed: 0
- Docs with the golden sensitivity, per run: run1: 21/24, run2: 21/24, run3: 21/24

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| shipped output (`unsafe` field; baseline: category == Unsafe) | 100% (15/15) | 71% (15/21) | the LLM's decision; positives in group: 7 |
| regex safety flag raised | 100% (3/3) | 14% (3/21) | secondary: any flag, even if not blocked; positives in group: 7 |

Label stability: 92% (22/24) of docs got the same category in all 3 runs; unstable: SYN05 [('Confidential', 2), ('Public', 1)], SYN10 [('Confidential', 2), ('Highly Sensitive', 1)]

Citation validity (LLM-produced citations only; code-generated PII/safety citations [42] carry redacted context and are not graded):

- LLM citations: 273; cited page exists: 100% (273/273); quote found on that page: 71% (195/273)
- Completed classifications with at least one valid citation: 88% (63/72)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00086, max $0.00134, total $0.0621
- total seconds: median 6.71, p90 9.48, mean 7.08
- API seconds: median 6.26, p90 9.17, mean 6.60
- input tokens mean 1287, output tokens mean 1467
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
