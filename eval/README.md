# Eval set (Phase 1a)

This folder holds the golden labels for the five datathon test cases (TC1-TC5) and 24 synthetic PDFs. They are used to score the classifier on two fields:
- `sensitivity`: Public, Confidential or Highly Sensitive
- `unsafe`: yes or no

Nothing here has been run against a model yet.

## Files

| File | What it holds |
|---|---|
| `golden.csv` | One row per document: label, `scored` flag, page and image counts, the two docx quotes the label derives from, and a notes column for decisions and conflicts. |
| `synthetic/SYNnn_*.pdf` | 24 synthetic documents: 8 Public, 7 Confidential, 9 Highly Sensitive (SYN23 was relabelled, decision 8). **Not committed.** `*.pdf` is already in `.gitignore`, so regenerate them. |
| `synthetic/pii_manifest.csv` | Every planted entity, with `doc_id, page, entity_type, value, modality, is_pii, note`. Rows with `is_pii=no` are decoys a detector should not flag. |
| `make_synthetic.py` | Writes all of the above. The CSVs are generated too, so do not edit them by hand. |

## Regenerate and check

```bash
python eval/make_synthetic.py --check
```

Requirements and determinism:
- The script needs Pillow 10.1 or later (`backend/requirements.txt` pins 10.1.0). `--check` also needs `pypdf`.
- The seed is fixed at 1729, no timestamps are written, and image pages are stored as Flate-compressed raw pixels.
- On Python 3.12.10 with Pillow 12.2.0, `--check` prints the PDF-set hash `54515af65bd01e66`.
- Text pages and both CSVs do not depend on the Pillow version. The image pages (SYN03, SYN13, SYN19, SYN20) may differ by a few bytes under the pinned Pillow, but their content and labels stay the same.

`--check` asserts that:
- every quote is a verbatim substring of the docx;
- every PDF's page count matches `golden.csv`, and synthetic PDFs open in pypdf strict mode;
- each class has 6-9 synthetic documents;
- no entity value repeats within a document;
- every text entity can be extracted from its stated page;
- no image entity appears in the extracted text, which proves those cases need OCR or vision.

## How labels are derived

Each label comes from one docx line, quoted in the row.

| Label | Docx rule quoted |
|---|---|
| TC1-TC5 sensitivity | That test case's "Expected Category: …" line |
| TC1-TC4 unsafe = no | "Content Safety: Content is safe for the kids." (a stub line, see decision 2) |
| Highly Sensitive | "Content that includes PII like SSNs, account/credit card numbers, and proprietary schematics" |
| Confidential | "Internal communications and business documents" / "customer details (names, addresses)" / "non-public operational content" |
| Public | "Marketing materials, product brochures, public website content, generic images." |
| unsafe = yes / no | "should not include Hate speech, exploitative, violent, criminal, political news or cyber-threat content". The label is yes if any listed kind is present. |

Precedence is inferred: any Highly Sensitive trigger makes the document Highly Sensitive. Otherwise any Confidential trigger makes it Confidential. Anything else is Public. `unsafe` is independent of `sensitivity`.

## Decisions (user, 2026-11-13)

1. **TC4 is Confidential**, following its test-case line, although the Highly Sensitive definition names military schematics (PLAN call 2). To avoid contradicting TC4, **SYN20** uses a non-military proprietary schematic for Highly Sensitive. That reading is accepted.
2. **The "Content Safety" line is a stub** copied across all five test cases, so it carries no information. For TC1-TC4, unsafe=no also matches the content; that is inferred.
3. **TC5 is not scored** (`scored=no`). The PDF does not match its docx description. It is a screen capture of a Word web editor showing page 1 of the same aviation manual as TC4, with no fighter and nothing confidential or unsafe. The docx label is kept for reference only. The capture shows an account name in the toolbar, which is not reproduced here.
4. **TC4 serial region**: the label "PORT SIDE F118-GE-100 TURBOFANS", top centre of the p9 cutaway image, to the right of "IN-FLIGHT REFUELING RECEPTACLE". It is an engine model designation, not a true serial number.
5. **Image count means every image placement** that pypdf reports (`page.images`), logos and icons included. TC2's 3 placements are 2 unique images.
6. **Business contacts and public figures are not PII** (`is_pii=no`). This covers company emails, phones and showroom addresses on public material, the fictional senator in SYN04, and the recruiter's number in SYN22.
7. **PDFs are regenerated, not committed.**
8. **SYN23 is Highly Sensitive** (Phase 3, `docs/FAILURES.md` F16). A minor's identity in a child-protection record counts as Highly Sensitive. This is a decision, not a docx derivation: the docx line quoted in its row names only SSNs, account/card numbers and schematics. The PDF is unchanged (set hash still `54515af65bd01e66`), and the file keeps its `conf_` name so saved run records still match. Numbers measured before this change are restated under the new label in `eval/runs_phase2/metrics_syn23_relabelled.md`.
9. **TC2 stays Highly Sensitive and the prompt definition is widened instead** (Phase 3, F2) to cover a private individual's application or personnel record. No label changed.

## Hard cases included

| Case | Docs |
|---|---|
| Public document with business contact details | SYN01, SYN04, SYN06, SYN07, SYN22 |
| Look-alike numbers (SSN-shaped order IDs) | SYN02 (Public), SYN10 (Confidential) |
| PII on a late page | SYN11 (p5 of 5), SYN18 (SSN on p6 of 6) |
| PII only inside an image-only page | SYN13 (customer name and address), SYN19 (name and SSN) |
| Image page without PII | SYN03 (marketing), SYN20 (schematic drawing) |
| Unsafe, Public level | SYN04 political news, SYN05 violent news, SYN22 exploitative (forced-labour job ad) |
| Unsafe, Confidential level | SYN12 cyber-threat |
| Unsafe, Highly Sensitive level | SYN21 criminal, SYN23 child safety (grooming indicators), SYN24 hate speech |

Every unsafe kind the docx lists now has at least one document. The unsafe examples are deliberately mild and non-graphic:
- The hate-speech line is dehumanising but contains no slurs.
- The child-safety case is grooming indicators only, with no sexual content.

## Fake-data conventions

- SSNs use area 9xx, which is never issued.
- Card numbers are published test numbers (4111…, 5555…4444, 4000 0566…).
- Phone numbers are 555-01xx, which is reserved for fiction.
- Emails use `example.com` or `.test`.
- Names, places and the politician are invented, and person names are unique across the set.
- Bank account numbers are random digits.
