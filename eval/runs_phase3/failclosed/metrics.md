## Metrics

Run metadata: `{"model": "claude-haiku-5-5", "sdk": "1.17.0", "python": "3.12.16", "pdf_set_hash": "54515af65bd01e66", "dual_verification": false, "runs": 3, "arm": {"input_mode": "text", "pii_hints": true, "fail_closed": true, "wide_hs": false, "max_tokens": 4096}, "started": "2026-11-14 01:02:53"}`

### TC1-TC4 (datathon test cases) (4 docs x 3 runs = 12 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = category Unsafe replaced the sensitivity (baseline output shape only), `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 3 | 0 | 0 | 0 | 0 | 100% (3/3) |
| Confidential | 0 | 6 | 0 | 0 | 0 | 100% (6/6) |
| Highly Sensitive | 0 | 3 | 0 | 0 | 0 | 0% (0/3) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 0% (0/9)
- Highly Sensitive predicted Public: 0% (0/3)
- Predicted Unsafe (sensitivity not measurable for these): 0; failed or unparsed: 0
- Docs with the golden sensitivity, per run: run1: 3/4, run2: 3/4, run3: 3/4

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| shipped output (`unsafe` field; baseline: category == Unsafe) | n/a | n/a | the LLM's decision; positives in group: 0 |
| regex safety flag raised | n/a | n/a | secondary: any flag, even if not blocked; positives in group: 0 |

Label stability: 100% (4/4) of docs got the same category in all 3 runs

Citation validity (LLM-produced citations only; code-generated PII/safety citations [3] carry redacted context and are not graded):

- LLM citations: 82; cited page exists: 100% (82/82); quote found on that page: 23% (19/82)
- Completed classifications with at least one valid citation: 67% (8/12)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00199, max $0.00297, total $0.0238
- total seconds: median 14.41, p90 27.60, mean 15.92
- API seconds: median 10.54, p90 13.34, mean 10.24
- input tokens mean 8251, output tokens mean 2321
- stop reasons: {'end_turn': 12}

### Synthetic (24 docs) (24 docs x 3 runs = 72 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = category Unsafe replaced the sensitivity (baseline output shape only), `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 13 | 8 | 3 | 0 | 0 | 54% (13/24) |
| Confidential | 0 | 17 | 4 | 0 | 0 | 81% (17/21) |
| Highly Sensitive | 0 | 0 | 27 | 0 | 0 | 100% (27/27) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 0% (0/48)
- Highly Sensitive predicted Public: 0% (0/27)
- Predicted Unsafe (sensitivity not measurable for these): 0; failed or unparsed: 0
- Docs with the golden sensitivity, per run: run1: 18/24, run2: 20/24, run3: 19/24

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| shipped output (`unsafe` field; baseline: category == Unsafe) | 100% (20/20) | 95% (20/21) | the LLM's decision; positives in group: 7 |
| regex safety flag raised | 100% (3/3) | 14% (3/21) | secondary: any flag, even if not blocked; positives in group: 7 |

Label stability: 92% (22/24) of docs got the same category in all 3 runs; unstable: SYN07 [('Confidential', 2), ('Public', 1)], SYN11 [('Confidential', 2), ('Highly Sensitive', 1)]

Citation validity (LLM-produced citations only; code-generated PII/safety citations [42] carry redacted context and are not graded):

- LLM citations: 276; cited page exists: 100% (276/276); quote found on that page: 80% (222/276)
- Completed classifications with at least one valid citation: 90% (65/72)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00089, max $0.00135, total $0.0640
- total seconds: median 7.09, p90 9.68, mean 7.33
- API seconds: median 6.55, p90 9.51, mean 6.97
- input tokens mean 1214, output tokens mean 1536
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
