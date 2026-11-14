# Features, evaluated (Phase 3)

Written 2026-11-13/14 on branch `claude/phase-3-features-da00dd`, cut from `main` at `9632beb` (Phase 2 merged). The base for every delta is `eval/runs_phase2/` (3 runs × 28 scored documents, PDF-set hash `54515af65bd01e66`).

Claim labels: **confirmed** (source named), **inferred**, **unknown**. Every number in a table is confirmed from the run records in `eval/runs_phase2/` and `eval/runs_phase3/<arm>/run*.jsonl` unless the row says otherwise.

## Verdicts

**Shipped: the fail-closed rule, with the widened Highly Sensitive definition and without the regex PII block (the `combo` arm). Those three settings are now the defaults.** TC1-TC4 go from 3/12 correct to 12/12, and the TC false-Public rate from 67% to 0%. Native PDF input is in the code and stays off.

| Candidate | Arm | Gate as written | Verdict |
|---|---|---|---|
| 1 + 3. Fail-closed rule, widened definition, no regex PII block | `combo` | passes | **Ship.** Defaults changed |
| 1, rule alone | `failclosed` | passes | **No-ship alone.** `combo` also fixes TC2 and does not disturb SYN07 or SYN11 |
| 1, definition alone | `widehs` | fails: no document fixed in 3/3 | **No-ship alone.** It ships inside `combo` and is your F2 decision |
| 3, alone | `f9` | fails: 1 document fixed in 3/3 | **No-ship alone.** It ships inside `combo` |
| 2. Native PDF input on top of the shipped defaults | `pdf_combo` | fails: cost +30.0% | **No-ship.** Same labels as `combo` on TC; it buys better citations and faster calls, at a cost the gate rules out |
| 2, with the widened definition only | `pdf_structured_widehs` | passes 1 to 3; cost +24.0% is in the borderline band | **No-ship.** It leaves TC3 and TC4 Public, and PDF mode on the shipped defaults is the row above |
| 2, PDF input alone | `pdf_structured` | fails: synthetic Highly Sensitive recall 100% → 93%; cost +23.3% | **No-ship** |
| 2, the two citation shapes | `pdf_citations`, `pdf_two_call` | fail on documents fixed, Highly Sensitive recall and cost | **No-ship** |

**Why I trust the `combo` result.** Three runs inside one arm are not independent (see the unsafe table), so the evidence I rest on is replication across separately run arms:

| Document | With the setting on | With it off |
|---|---|---|
| TC3, fail-closed rule | 9/9 correct (3 arms) | 0/24 (the base and 7 arms) |
| TC4, fail-closed rule | 9/9 correct (3 arms) | 0/24 (the base and 7 arms) |
| TC2, widened definition | 11/12 correct (4 arms; the twelfth is a parse failure) | 0/21 (the base and 6 arms) |

**What shipping costs:**

- **Two Public documents become Confidential.** With the rule on, SYN22 is wrong in 9/9 runs and SYN05 in 7/9; with it off SYN22 is right in 23/24 runs and SYN05 in 24/24. Synthetic Public recall falls from 88% to 67%. Over-classification is the safe direction, and SYN22 still carries `unsafe: true` in every run.
- **SYN23 loses its unsafe flag more often (inferred).** With the widened definition it is flagged in 7/12 runs, without it in 21/21.
- **Cost +2.8%, API seconds −5% (TC) and −3% (synthetic):** inside the run-to-run band.

**What this eval could not settle: unsafe recall.** Phase 2's 100% does not replicate. The `control` arm sent the same request 4.5 hours later and scored 81% (17/21). `combo` scored 71% (15/21), which cannot be told apart from that. See "Unsafe recall" below.

**To go back to the Phase 2 prompt,** set `PROMPT_PII_HINTS=true`, `PROMPT_FAIL_CLOSED=false` and `PROMPT_WIDE_HS=false` in `.env`.

## Decisions you made (2026-11-13)

| Topic | Decision |
|---|---|
| F2, TC2 | Widen the Highly Sensitive definition to cover a private individual's application or personnel record. TC2 stays golden Highly Sensitive. |
| F16, SYN23 | Relabel SYN23 Highly Sensitive: a minor's identity in a child-protection record. The prompt definition gains that line. |
| Gate | Fixing over-classification counts: a candidate also ships if it fixes at least 2 over-classified documents in all 3 runs. |
| Spend | $2.00 cap for all Phase 3 paid runs, enforced on the summed `count_tokens` estimate. |

## The ship gate, fixed before any paid result

A candidate ships only if all of these hold against `eval/runs_phase2/`:

1. **It improves something that counts:** the false-Public rate, Highly Sensitive recall, or (your decision) over-classification.
2. **Two documents:** at least 2 documents wrong in the base are right in all 3 runs.
3. **No TC1-TC4 regression,** and no loss in false-Public rate or Highly Sensitive recall anywhere.
4. **Cost and latency not worse,** read against the run-to-run spread below.

**Noise band** (confirmed: per-run means computed from `eval/runs/run*.jsonl` and `eval/runs_phase2/run*.jsonl`). The same code on the same documents varies between runs by this much:

| Metric | TC1-TC4, 3 runs | Synthetic, 3 runs | Largest spread |
|---|---|---|---|
| Cost per classification, mean (Phase 2) | $0.00193 to $0.00202 | $0.00083 to $0.00084 | 5% |
| Total seconds, median (Phase 2) | 14.7 to 15.9 | 6.8 to 7.5 | 10% |
| API seconds, median (Phase 2) | 9.8 to 11.3 | 6.3 to 6.5 | 15% |

So "not worse" means: pooled mean cost within +5% of the base, and median API seconds within +15%. Anything between those bounds and +25% is reported as borderline and left to you. I use API seconds for the latency call because total seconds also includes local OCR, which no candidate changes.

**What the gate does not cover.** It names no limit for unsafe recall or for new over-classification, because the base had 100% unsafe recall and no candidate targeted it. I did not change the gate after seeing results. Each arm below gets two readings: the gate as written, and what moved outside it.

## The base under the SYN23 relabel

Relabelling SYN23 changes the base numbers without any model change, so every table below uses the restated base (confirmed: `eval/runs_phase2/metrics_syn23_relabelled.md`, which differs from `metrics.md` in 4 lines).

| Synthetic metric | As measured in Phase 2 | Restated |
|---|---|---|
| Recall Confidential | 75% (18/24) | 86% (18/21) |
| Recall Highly Sensitive | 100% (24/24) | 100% (27/27) |
| Docs correct per run | 21, 21, 21 | 22, 22, 22 |

This gain is a label change, not an improvement. The documents still wrong in the base are TC2, TC3, TC4, SYN02 and SYN10, each in 3/3 runs.

## Shortlist, ranked against `docs/FAILURES.md`

| Rank | Candidate | Failures it targets | Why this rank |
|---|---|---|---|
| 1 | **Fail-closed decision rule, with the widened Highly Sensitive definition** (prompt text only) | F1: TC3 and TC4 called Public in 3/3. F2: TC2 called Confidential in 3/3 | False-Public is the costliest error and accounts for 6 of the 9 wrong TC answers per 3 runs. Costs nothing per call. |
| 2 | **Native PDF input with citations and structured output** (mandatory; three request shapes) | F13: quote on the cited page 71% synthetic, 36% TC. F1 on TC4: the cutaway on page 9 is an image that text mode never sees | The only candidate that can reach the citation failures and the image. |
| 3 | **Stop sending the regex PII result to the model** | F9: SSN-shaped order IDs make SYN02 and SYN10 Highly Sensitive in 3/3 | Two documents, both over-classified, so it counts only under your gate decision. |

Not shortlisted, with the evidence in "Verdicts that needed no spend" below: a confidence gate, a regex-PII rule, and a second pass or bigger tier behind a confidence gate.

## What ran

Each arm changes the settings shown and nothing else. Settings not shown were at the Phase 2 values: `LLM_INPUT_MODE=text`, `PROMPT_PII_HINTS=true`, `PROMPT_FAIL_CLOSED=false`, `PROMPT_WIDE_HS=false`. The code defaults changed after the runs, so to reproduce an arm name all four. Every arm is 3 runs × 28 documents on `claude-haiku-5-5`, compared with `python eval/run_eval.py compare --base eval/runs_phase2 --dir <arm dir>`.

| Arm | Settings | Candidate |
|---|---|---|
| `f9` | `PROMPT_PII_HINTS=false` | 3 |
| `failclosed` | `PROMPT_FAIL_CLOSED=true` | 1 |
| `widehs` | `PROMPT_WIDE_HS=true` | 1 |
| `combo` | the three text switches together | 1 + 3 |
| `pdf_structured` | `LLM_INPUT_MODE=pdf_structured`, `MAX_TOKENS=8192` | 2 |
| `pdf_citations` | `LLM_INPUT_MODE=pdf_citations`, `MAX_TOKENS=8192` | 2 |
| `pdf_two_call` | `LLM_INPUT_MODE=pdf_two_call`, `MAX_TOKENS=8192` | 2 |
| `control` (round 2) | none: the Phase 2 settings on the Phase 3 code | drift check |
| `pdf_structured_widehs` (round 2) | `LLM_INPUT_MODE=pdf_structured`, `PROMPT_WIDE_HS=true`, `MAX_TOKENS=8192` | 2 + your F2 decision |
| `pdf_combo` (round 2) | `LLM_INPUT_MODE=pdf_structured` with the three text switches, `MAX_TOKENS=8192` | 1 + 2 + 3 |

- **Why round 2:** round 1 showed unsafe recall falling in six of seven arms, and no arm had rerun the default settings. `control` is that rerun. The two PDF arms test the mandatory candidate with the definition you chose for F2, and with everything together.
- **Failures:** 1 of 840 classifications. `widehs` run 3 on TC2 returned no parseable sensitivity (cause: parse; stop reason `end_turn`). No refusal, truncation or API outage in any arm.
- **Spend:** $0.957 measured from the records ($0.661 in round 1, $0.296 in round 2), against summed `count_tokens` estimates of $0.866 and $0.335. The ten smoke tests (3 documents each) wrote no records; from the same documents' costs they add about $0.07 (inferred). The total is about $1.03 of the $2.00 cap.

## Docs read before writing the request code

| Page | What I took from it |
|---|---|
| PDF support, `platform.claude.com/docs/en/build-with-claude/pdf-support` | The `document` block with a base64 `application/pdf` source, placed before the text. Each page is sent as text plus an image. |
| Citations, `platform.claude.com/docs/en/build-with-claude/citations` | `citations: {enabled: true}` per document. PDF citations are `page_location` with a 1-indexed `start_page_number`. Only text is citable, not images or scanned pages. Citations cannot be combined with structured outputs in one request. |
| Structured outputs, `platform.claude.com/docs/en/build-with-claude/structured-outputs` | `output_config.format` with a JSON schema. No numeric bounds in the schema. A refusal or a `max_tokens` stop can break the schema, so the code checks the stop reason. |
| Models API (`client.models.retrieve`). The call shape comes from the Claude API reference bundled with Claude Code (`shared/models.md`), not from a page I fetched. Result saved in `eval/runs_phase3/models_api.json` | `claude-haiku-5-5` reports `pdf_input`, `citations` and `structured_outputs` as supported (confirmed by the live call). |

## Results, TC1-TC4 (12 classifications per arm)

| Arm | Correct | False-Public | Highly Sensitive recall | Fixed in 3/3 | Regressed | Cost, mean | API s, median |
|---|---|---|---|---|---|---|---|
| base | 3/12 | 67% (6/9) | 0% (0/3) | | | $0.00199 | 11.08 |
| `f9` | 3/12 | 67% (6/9) | 0% (0/3) | none | none | $0.00204 | 11.00 |
| `failclosed` | 9/12 | **0% (0/9)** | 0% (0/3) | TC3, TC4 | none | $0.00199 | 10.54 |
| `widehs` | 5/12 | 67% (6/9) | 67% (2/3) | none (TC2 2/3, the third run failed to parse) | none | $0.00193 | 9.58 |
| `combo` | **12/12** | **0% (0/9)** | **100% (3/3)** | TC2, TC3, TC4 | none | $0.00201 | 10.50 |
| `pdf_structured` | 3/12 | 67% (6/9) | 0% (0/3) | none | none | $0.00263 | 6.73 |
| `pdf_citations` | 3/12 | 67% (6/9) | 0% (0/3) | none | none | $0.00298 | 6.62 |
| `pdf_two_call` | 3/12 | 67% (6/9) | 0% (0/3) | none | none | $0.00181 (cache-warmed, see below) | 10.26 |
| `control` | 3/12 | 67% (6/9) | 0% (0/3) | none | none | $0.00203 | 10.88 |
| `pdf_structured_widehs` | 6/12 | 67% (6/9) | **100% (3/3)** | TC2 | none | $0.00264 | 6.94 |
| `pdf_combo` | **12/12** | **0% (0/9)** | **100% (3/3)** | TC2, TC3, TC4 | none | $0.00273 | 6.68 |

## Results, synthetic (72 classifications per arm)

"Over-classified" counts a Public document called anything else, or a Confidential document called Highly Sensitive. The false-Public rate is 0% (0/48) in the base and in every arm, so it has no column.

| Arm | Correct | Public recall | Highly Sensitive recall | Over-classified | Unsafe recall | Fixed in 3/3 | Regressed (sensitivity) | Cost, mean | API s, median |
|---|---|---|---|---|---|---|---|---|---|
| base | 66/72 | 88% (21/24) | 100% (27/27) | 8% (6/72) | 100% (21/21) | | | $0.00083 | 6.47 |
| `f9` | 70/72 | 92% (22/24) | 100% (27/27) | 3% (2/72) | 86% (18/21) | SYN10 (SYN02 2/3) | SYN22 → 2/3 | $0.00079 | 5.71 |
| `failclosed` | 57/72 | 54% (13/24) | 100% (27/27) | 21% (15/72) | 95% (20/21) | none | SYN05 → 0/3, SYN22 → 0/3, SYN07 → 1/3, SYN11 → 2/3 | $0.00089 | 6.55 |
| `widehs` | 69/72 | 92% (22/24) | 100% (27/27) | 4% (3/72) | 90% (19/21) | none (SYN10 2/3, SYN02 1/3) | none | $0.00082 | 6.24 |
| `combo` | 63/72 | 67% (16/24) | 100% (27/27) | 12% (9/72) | 71% (15/21) | none (SYN10 2/3) | SYN22 → 0/3, SYN05 → 1/3 | $0.00086 | 6.26 |
| `pdf_structured` | 70/72 | 100% (24/24) | 93% (25/27) | 0% (0/72) | 90% (19/21) | SYN02, SYN10 | SYN23 → 1/3 | $0.00100 | 5.05 |
| `pdf_citations` | 68/72 | 96% (23/24) | 89% (24/27) | 1% (1/72) | 100% (21/21) | SYN10 (SYN02 2/3) | SYN23 → 0/3 | $0.00101 | 4.45 |
| `pdf_two_call` | 70/72 | 96% (23/24) | 96% (26/27) | 1% (1/72) | 90% (19/21) | SYN10 (SYN02 2/3) | SYN23 → 2/3 | $0.00124 (cache-warmed) | 7.49 |
| `control` | 68/72 | 88% (21/24) | 100% (27/27) | 6% (4/72) | 81% (17/21) | none (SYN10 2/3) | none | $0.00082 | 6.40 |
| `pdf_structured_widehs` | 71/72 | 96% (23/24) | 100% (27/27) | 1% (1/72) | 100% (21/21) | SYN10 (SYN02 2/3) | none | $0.00100 | 4.78 |
| `pdf_combo` | 64/72 | 67% (16/24) | 100% (27/27) | 11% (8/72) | 90% (19/21) | SYN10 | SYN22 → 0/3, SYN05 → 1/3 | $0.00106 | 5.00 |

## The gate as written, per arm

Cost is the pooled mean over all 84 classifications against the base's $0.000998. API seconds are the group medians against 11.08 (TC) and 6.47 (synthetic).

| Arm | 1. Improves | 2. Two documents in 3/3 | 3. No TC regression, no false-Public or HS-recall loss | 4. Cost / API seconds | Gate |
|---|---|---|---|---|---|
| `f9` | over-classification 8% → 3% | no: SYN10 only | yes | −3.4% / −1%, −12% | **fails (2)** |
| `failclosed` | TC false-Public 67% → 0% | yes: TC3, TC4 | yes | +4.8% / −5%, +1% | **passes** |
| `widehs` | TC HS recall 0% → 67% | no: none | yes | −1.7% / −14%, −4% | **fails (2)** |
| `combo` | TC false-Public 67% → 0%, TC HS recall 0% → 100% | yes: TC2, TC3, TC4 | yes | +2.8% / −5%, −3% | **passes** |
| `pdf_structured` | over-classification 8% → 0% | yes: SYN02, SYN10 | no: synthetic HS recall 100% → 93% | +23.3% (borderline) / −39%, −22% | **fails (3)**, borderline on cost |
| `pdf_citations` | over-classification 8% → 1% | no: SYN10 only | no: synthetic HS recall 100% → 89% | +29.3% / −40%, −31% | **fails (2, 3, 4)** |
| `pdf_two_call` | over-classification 8% → 1% | no: SYN10 only | no: synthetic HS recall 100% → 96% | +32.6% warmed, about +130% cold / −7%, +16% | **fails (2, 3, 4)** |
| `pdf_structured_widehs` | TC HS recall 0% → 100%, over-classification 8% → 1% | yes: TC2, SYN10 | yes | +24.0% (borderline) / −37%, −26% | **passes 1 to 3; cost is in the band left to you** |
| `pdf_combo` | TC false-Public 67% → 0%, TC HS recall 0% → 100% | yes: TC2, TC3, TC4, SYN10 | yes | +30.0% / −40%, −23% | **fails (4)** |

`control` is not a candidate. Against the base it costs −0.6% and its API medians are −2% and −1%, so cost and latency did not drift between the two sessions.

**SYN10 is a weak witness in any single arm:** `control` got it right in 2 of 3 runs with nothing changed. Across the five PDF arms it is right in 15/15 runs, which is the evidence that PDF input fixes it.

## Outside the gate: what else moved

### Over-classification of Public documents

The fail-closed rule fixes two or three TC documents and breaks two synthetic Public documents in the same currency:

| Arm | Fixed in 3/3 | Public documents now called Confidential |
|---|---|---|
| `failclosed` | TC3, TC4 | SYN05 0/3, SYN22 0/3, SYN07 1/3 |
| `combo` | TC2, TC3, TC4 | SYN22 0/3, SYN05 1/3 (and SYN02 still wrong, now Confidential instead of Highly Sensitive) |
| `pdf_combo` | TC2, TC3, TC4, SYN10 | SYN22 0/3, SYN05 1/3 (SYN02 as in `combo`) |

- **Mechanism (confirmed from the saved reasoning):** the rule lists marketing materials, brochures, website content and generic images. The model reads that list literally, so a community newsletter (SYN05), a job advert (SYN07, SYN22) and a support FAQ (SYN02) are "not shown to be produced for public release".
- **With the PII block left in (`failclosed`),** step 1 of the rule plus "SSN, high severity" from the regex keeps SYN02 and SYN10 Highly Sensitive in 3/3 and pushes SYN11 there once. The saved reasoning says "Decision rule step 1 applies. The PII detector reported SSN-type data at high severity".
- **The effect is real, not drift:** `combo` and `pdf_combo` are separate runs and break the same two documents by the same counts, while `control` keeps both at 3/3.
- **Both broken documents are unsafe ones.** SYN22 keeps `unsafe: true` in 3/3 runs of both arms, so it still goes to human review.
- **This is the same trade as the 0.90 confidence row** in the replay table below, with one difference: the rule was written before any result, while 0.90 was picked by looking at these documents.

### Unsafe recall

Correct `unsafe` answers out of 3 runs, for the seven documents whose golden label is unsafe:

| Arm | SYN04 | SYN05 | SYN12 | SYN21 | SYN22 | SYN23 | SYN24 | Recall |
|---|---|---|---|---|---|---|---|---|
| base | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 100% (21/21) |
| `f9` | 3 | 2 | 3 | 3 | 3 | 3 | 1 | 86% (18/21) |
| `failclosed` | 3 | 2 | 3 | 3 | 3 | 3 | 3 | 95% (20/21) |
| `widehs` | 3 | 3 | 3 | 3 | 3 | 1 | 3 | 90% (19/21) |
| `combo` | 3 | 0 | 3 | 2 | 3 | 1 | 3 | 71% (15/21) |
| `pdf_structured` | 3 | 1 | 3 | 3 | 3 | 3 | 3 | 90% (19/21) |
| `pdf_citations` | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 100% (21/21) |
| `pdf_two_call` | 3 | 1 | 3 | 3 | 3 | 3 | 3 | 90% (19/21) |
| **`control`** | 3 | 3 | 3 | 2 | 3 | 3 | **0** | **81% (17/21)** |
| `pdf_structured_widehs` | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 100% (21/21) |
| `pdf_combo` | 3 | 2 | 3 | 3 | 3 | 2 | 3 | 90% (19/21) |

Unsafe precision is 100% in every arm.

**How to read this table:**

- **The unsafe answer moves on its own.** `control` sent the same request as the base 4.5 hours later (start times in the two `meta.json` files) and lost 4 of 21. The request is confirmed the same: input-token counts match on all 28 documents, and the text-mode `messages.create` call has the same arguments as on `main`. SYN24 went from 3/3 to 0/3 and SYN21 to 2/3. The base's 21/21 was the lucky end of the range.
- **So no arm's unsafe recall can be told apart from the control's 17/21.** The arms range from 15/21 to 21/21. "Candidate X lowers unsafe recall" is not supported by this data, and neither is "candidate X keeps it".
- **Runs inside one arm are not independent.** A document usually goes 3/3 or 0/3 within an arm and differs between arms run at different times. Three runs in one session understate the real spread for unsafe (confirmed by `control`). For sensitivity the control moved one document, SYN10, in 2 of 3 runs.
- **One effect does look real (inferred): the widened definition on SYN23.** With `PROMPT_WIDE_HS` on, SYN23 is flagged unsafe in 7 of 12 runs (four arms). With it off, 21 of 21 (the base and six arms). The new line names safeguarding records as Highly Sensitive, and the model then tends to treat the report as a protective record instead of unsafe content.
- **One shared suspect (inferred, not tested):** the prompt tells the model the regex safety check result, and that regex has 14% recall (3/21). Two saved answers mention it: "the content safety check passed" (`pdf_structured`, SYN05) and "despite the tool's "safe" result" (`pdf_citations`, SYN23, where the model overrode it). This is the unsafe-side twin of F9.
- **Limit of the evidence:** the eval records keep the first 300 characters of the model's reasoning, so the unsafe rationale is cut off in most records.

## The three request shapes for native PDF input

| | One call, citations on, reply parsed from lines (`pdf_citations`) | Two calls, PDF cache-marked (`pdf_two_call`) | One structured call, quotes checked in code (`pdf_structured`) |
|---|---|---|---|
| API calls per document | 1 | 2 | 1 |
| Correct, TC / synthetic | 3/12, 68/72 | 3/12, 70/72 | 3/12, 70/72 |
| Parse failures | 0/84 | 0/84 | 0/84 |
| Cost against the base, pooled | +29.3% | +32.6% as measured, about +130% cold | +23.3% |
| API seconds, median, TC / synthetic (base 11.08 / 6.47) | 6.62 / 4.45 | 10.26 / 7.49 | 6.73 / 5.05 |
| Quote found on the cited page, TC / synthetic (base 36% / 71%) | 52% (33/64) / 100% (227/227) | 58% (53/92) / 98% (292/297) | 70% (30/43) / 100% (253/253) |
| Evidence lines with no citation attached | 25 | 54 | 0 (the schema requires a page and a quote) |
| Classifications with no page citation at all | 3/84 | 0/84 | 0/84 |
| Image regions cited | 0 (not possible) | 0 (not possible) | 8, described in words |
| Unsafe recall (not a ranking: an unchanged rerun scored 17/21) | 21/21 | 19/21 | 19/21 |

- **Why PDF input costs more and runs faster:** each page is sent as text plus an image, so mean input tokens rise from 8,038 to 20,781 on TC and from 1,001 to 5,275 on synthetic (`pdf_structured`). Mean output tokens fall from 2,368 to 1,106 on TC and from 1,467 to 941 on synthetic, and output is what takes the time.
- **The cache is never hit within one classification (confirmed).** In run 1 of `pdf_two_call`, all 25 documents that the smoke test had not touched show `cache_read` 0 on both calls, and both calls pay a cache write. The first call sets `output_config.format` and the second turns citations on, and each of those changes what the cache matches on, so the second call cannot reuse the first call's PDF. The Structured outputs page says so for `output_config.format`; for the citations switch my source is the prompt-caching reference bundled with Claude Code, not a page I fetched.
- **So the measured `pdf_two_call` cost is too low.** Runs 2 and 3 read the cache that run 1 wrote for the same document, and the smoke test warmed TC1, TC4 and SYN07. A production document is classified once. On the 25 cold documents in run 1 the mean cost is $0.00198 on synthetic (base, same documents: $0.00084) and $0.00349 on TC2 and TC3 (base: $0.00155).
- **Citations API quotes against this pipeline's page text:** an API citation is a valid pointer by construction. The 52% and 58% on TC measure how often the API's extracted text matches the text pypdf and OCR produce for the same page, not how often the citation is wrong.
- **Best of the three: `pdf_structured`.** It is the cheapest, it never leaves an evidence line without a page, and it is the only one that can point at an image. Its quote check runs in code and sets `verified: false` on a quote that is not on the page (30% of TC quotes, 0% of synthetic).
- **The switches carry over to PDF input.** `pdf_structured_widehs` fixes TC2 in 3/3 and keeps SYN23 Highly Sensitive in 3/3, which confirms that the round 1 recall loss came from the missing definition. `pdf_combo` fixes the same three TC documents as `combo` and breaks the same two synthetic ones.
- **One confound in the F13 gain:** the `pdf_structured` prompt also tells the model to copy quotes word for word, so the rise from 71% to 100% is the prompt line and the PDF input together.

### The region gap

The docx asks for TC4 to "cite the region with the serial". The golden region is the label "PORT SIDE F118-GE-100 TURBOFANS" on the page-9 cutaway.

- **Citations API:** it returns page numbers for text only. It cannot cite an image, so it cannot close this gap (confirmed: Citations page; 0 image citations in both citation arms).
- **`pdf_structured`:** it cited the page-9 cutaway as an image region in 3/3 runs, for example "Full-width cutaway line drawing of a flying-wing stealth bomber near the top of the page". It never named the F118 label, and a described region has no coordinates that code can check.
- **Seeing the image did not change the label.** All four PDF arms without the fail-closed rule call TC4 Public in 3/3. Only the rule moves TC4, in text mode and in PDF mode alike.
- **The image citation is not reliable from run to run.** `pdf_structured_widehs` cited the cutaway in 3/3 and once listed the "in-flight refueling receptacle" callout that sits next to the golden label. `pdf_combo` did not cite the cutaway in any run.

## Verdicts that needed no spend: replay on the saved Phase 2 records

A rule applied in code after the model's answer can be replayed on `eval/runs_phase2/run*.jsonl`. All rows are confirmed by that replay.

| Rule | Fixed in 3/3 | Regressed | Verdict |
|---|---|---|---|
| Public with confidence < 0.85 becomes Confidential (0.85 is the existing `CONFIDENCE_THRESHOLD`) | TC3 | SYN05 3/3 → 1/3 | **No-ship:** 1 document, and a regression |
| Same, threshold 0.86 | TC3 (TC4 only 2/3) | SYN04 and SYN05 3/3 → 0/3 | **No-ship** |
| Same, threshold 0.90 | TC3, TC4 | SYN04 and SYN05 3/3 → 0/3; SYN07 and SYN22 3/3 → 2/3 | **No-ship, your call:** see below |
| Public with any regex PII hit becomes Confidential | none | SYN01, SYN04, SYN06, SYN07 3/3 → 0/3 | **No-ship:** the regex fires on business emails, and on neither TC3 nor TC4 |
| Second pass or bigger tier when confidence < 0.85 | not run | not run | **Not run:** it would reach TC3, SYN02, SYN10, SYN05 and SYN20 only. TC2 (0.85) and TC4 (0.85 to 0.88) are never escalated |

- **Why the confidence rule fails:** the model's confidence does not separate right from wrong. TC4 is wrong at 0.85 to 0.88 while SYN04 and SYN05 are right at 0.80 to 0.85.
- **The 0.90 row:** it takes the TC false-Public rate from 67% to 0% at no cost, and it meets the gate as written. I still mark it no-ship because 0.90 is the one threshold that works and I found it by looking at these 28 documents. It also turns two correct Public documents into Confidential in every run. The shipped fail-closed rule now fixes TC3 and TC4 without this threshold and leaves SYN04 correct, so the rule is no longer needed.
- **Tier escalation:** the brief allows a bigger model only where the eval shows a gap it closes. A confidence gate cannot route TC2 or TC4 to it, so the gap it could close is TC3 alone, which is under the 2-document rule. Not run, so what Sonnet 5.5 would answer on these documents is unknown.

## What is in the code

| Setting | Default now | Phase 2 behaviour | What it does |
|---|---|---|---|
| `PROMPT_FAIL_CLOSED` | `true` | `false` | Adds the decision rule: Public only on clear evidence |
| `PROMPT_WIDE_HS` | `true` | `false` | Adds the personnel-record and safeguarding lines to the Highly Sensitive definition |
| `PROMPT_PII_HINTS` | `false` | `true` | `true` puts the regex PII block back into the prompt |
| `LLM_INPUT_MODE` | `text` | `text` | `pdf_structured`, `pdf_citations` or `pdf_two_call` send the PDF itself (for `.pdf` files and Claude models only). Every PDF arm was measured with `MAX_TOKENS=8192`; the default is 4096, and a reply cut off at the limit now fails the classification, so set both together |

- **Shipped equals measured (confirmed):** with the new defaults and no overrides, the prompt length matches the `combo` arm's saved `prompt_chars` on 28 of 28 documents (`eval/run_eval.py estimate --offline`).
- **Always on, no setting:** a refusal or a `max_tokens` stop now fails the classification instead of being parsed, and each model-written quote gets `verified: true/false` from a check against the cited page.
- **Tests:** `python -m pytest -q test_system.py` in the `docclf-eval:phase3` image with `.env` masked gives 31 passed, 4 xfailed, run after the defaults changed. `test_prompt_switches` asserts the new defaults.

## Reproduce

Estimate first, then run, then compare. The key is passed by name and `.env` is masked with an empty file. This example is the `failclosed` arm; take the four settings for another arm from "What ran".

```bash
docker run --rm -e ANTHROPIC_API_KEY -e LLM_INPUT_MODE=text -e PROMPT_PII_HINTS=true -e PROMPT_FAIL_CLOSED=true -e PROMPT_WIDE_HS=false -v "$PWD":/app -v <empty-file>:/app/.env:ro -w /app docclf-eval:phase3 python eval/run_eval.py estimate --runs 3 --dir eval/runs_phase3/failclosed
```

```bash
docker run --rm -e ANTHROPIC_API_KEY -e LLM_INPUT_MODE=text -e PROMPT_PII_HINTS=true -e PROMPT_FAIL_CLOSED=true -e PROMPT_WIDE_HS=false -v "$PWD":/app -v <empty-file>:/app/.env:ro -w /app docclf-eval:phase3 python eval/run_eval.py run --runs 3 --dir eval/runs_phase3/failclosed
```

```bash
docker run --rm -v "$PWD":/app -v <empty-file>:/app/.env:ro -w /app docclf-eval:phase3 python eval/run_eval.py compare --base eval/runs_phase2 --dir eval/runs_phase3/failclosed
```

**Base for later phases:** a bare eval run with no overrides now reproduces `combo`, so later deltas should compare against `eval/runs_phase3/combo`, not `eval/runs_phase2`.

Each arm's folder holds `meta.json` (the settings it ran with), `estimate.json`, `run1-3.jsonl`, `metrics.md` and `compare.md`. The PDF arms also set `MAX_TOKENS=8192`.

## Adjacent issues, listed and not fixed

- **The `unsafe` answer is unstable on an unchanged request.** SYN24 went from 3/3 to 0/3 between Phase 2 and the `control` rerun. Phase 2's 100% unsafe recall should be read as 81% to 100%, and three runs in one session do not show the spread. This needs its own entry in `docs/FAILURES.md`.
- **Regex safety result in the prompt:** the model is told "Content is Safe: Yes" from a check with 14% recall. Untested as a candidate; see the unsafe table.
- **Eval records cut reasoning at 300 characters** (`eval/run_eval.py:172`), which hid most unsafe rationales in this phase.
- **`eval/README.md:7`** still says "Nothing here has been run against a model yet."
- **Four xfail reasons in `test_system.py`** cite `FAILURES.md` ids F10, F8, F7 and F9 where the document says F12, F10, F9 and F11.
- **The `verified` flag on a citation is not stored in the database**, only returned.
- **`unsafe` still fails open** when the model's answer has no usable value (the F3 limitation).
- **Not run:** a Sonnet 5.5 probe on the documents Haiku still gets wrong.
