## Metrics

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
