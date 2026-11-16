## Metrics

Run metadata: `{"model": "claude-haiku-5-5", "sdk": "1.17.0", "python": "3.12.15", "pdf_set_hash": "54515af65bd01e66", "dual_verification": false, "runs": 3, "arm": {"input_mode": "text", "pii_hints": false, "fail_closed": true, "wide_hs": true, "max_tokens": 4096}, "commit": "660c141af9ebf1199d2707da48610456b65895b9", "dirty": false, "started": "2026-11-16 07:34:32"}`

### TC1-TC4 (datathon test cases) (4 docs x 3 runs = 12 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = category Unsafe replaced the sensitivity (baseline output shape only), `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 3 | 0 | 0 | 0 | 0 | 100% (3/3) |
| Confidential | 0 | 6 | 0 | 0 | 0 | 100% (6/6) |
| Highly Sensitive | 0 | 0 | 2 | 0 | 1 | 67% (2/3) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 0% (0/9)
- Highly Sensitive predicted Public: 0% (0/3)
- Predicted Unsafe (sensitivity not measurable for these): 0; failed or unparsed: 1
- Docs with the golden sensitivity, per run: run1: 4/4, run2: 4/4, run3: 3/4

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| shipped output (`unsafe` field; baseline: category == Unsafe) | n/a | n/a | the LLM's decision; positives in group: 0 |
| regex safety flag raised | n/a | n/a | secondary: any flag, even if not blocked; positives in group: 0 |

Label stability: 75% (3/4) of docs got the same category in all 3 runs; unstable: TC2 [('Highly Sensitive', 2), ('Other', 1)]

Citation validity (LLM-produced citations only; code-generated PII/safety citations [2] carry redacted context and are not graded):

- LLM citations: 88; cited page exists: 100% (88/88); quote found on that page: 27% (24/88)
- Completed classifications with at least one valid citation: 91% (10/11)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00205, max $0.00322, total $0.0246
- total seconds: median 12.44, p90 14.94, mean 12.14
- API seconds: median 10.14, p90 12.83, mean 10.61
- input tokens mean 8327, output tokens mean 2435
- stop reasons: {'end_turn': 12}

### Synthetic (24 docs) (24 docs x 3 runs = 72 classifications)

Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). `Unsafe` = category Unsafe replaced the sensitivity (baseline output shape only), `Other` = Unknown/failed.

| golden \ predicted | Public | Confidential | Highly Sensitive | Unsafe | Other | recall |
|---|---|---|---|---|---|---|
| Public | 16 | 8 | 0 | 0 | 0 | 67% (16/24) |
| Confidential | 0 | 21 | 0 | 0 | 0 | 100% (21/21) |
| Highly Sensitive | 0 | 0 | 27 | 0 | 0 | 100% (27/27) |

- False-Public rate (Confidential or Highly Sensitive predicted Public): 0% (0/48)
- Highly Sensitive predicted Public: 0% (0/27)
- Predicted Unsafe (sensitivity not measurable for these): 0; failed or unparsed: 0
- Docs with the golden sensitivity, per run: run1: 21/24, run2: 22/24, run3: 21/24

Unsafe detection (pooled over runs):

| signal | precision | recall | note |
|---|---|---|---|
| shipped output (`unsafe` field; baseline: category == Unsafe) | 100% (21/21) | 100% (21/21) | the LLM's decision; positives in group: 7 |
| regex safety flag raised | 100% (3/3) | 14% (3/21) | secondary: any flag, even if not blocked; positives in group: 7 |

Label stability: 96% (23/24) of docs got the same category in all 3 runs; unstable: SYN22 [('Confidential', 2), ('Public', 1)]

Citation validity (LLM-produced citations only; code-generated PII/safety citations [42] carry redacted context and are not graded):

- LLM citations: 270; cited page exists: 100% (270/270); quote found on that page: 74% (201/270)
- Completed classifications with at least one valid citation: 88% (63/72)

Cost and latency per classification (pooled; latency includes OCR in total, API only in api):

- cost: mean $0.00086, max $0.00133, total $0.0621
- total seconds: median 6.51, p90 9.10, mean 6.82
- API seconds: median 6.08, p90 8.96, mean 6.58
- input tokens mean 1287, output tokens mean 1469
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

By cause: {'parse': 1}

- TC2 run3: model returned no valid sensitivity: 'Unknown'
