"""Baseline eval for the document classifier (PLAN Phase 1, steps 4-5).

Run inside the Docker image (needs tesseract, poppler, libmagic):

    python eval/run_eval.py estimate [--offline]   # token/cost estimate, no paid generation
    python eval/run_eval.py run [--runs 3]         # PAID: regenerates PDFs, classifies, writes eval/runs/*.jsonl
    python eval/run_eval.py report [--out FILE]    # metrics (markdown) from eval/runs/*.jsonl

The classifier code is NOT modified: usage/latency come from wrapping the SDK call,
page text from wrapping the document processor, so every metric is measured on the
shipped output shape. Metrics the shape cannot express are reported as not measurable.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

EVAL = Path(__file__).resolve().parent
ROOT = EVAL.parent
RUNS = EVAL / "runs"
MODEL = "claude-haiku-5-5"
# $/token, claude-api skill shared/model-migration.md (Haiku 5.5): <=100K-token prompt vs longer
RATE_SHORT = (0.10 / 1e6, 0.50 / 1e6)
RATE_LONG = (0.50 / 1e6, 2.50 / 1e6)
SENS = ["Public", "Confidential", "Highly Sensitive"]
OUT_TOKENS = {"low": 600, "mid": 1500, "high": 4096}  # assumptions; 4096 = MAX_TOKENS cap incl. thinking
PII_MAP = {"ssn": "SSN", "credit_card": "CREDIT_CARD", "email": "EMAIL", "phone": "PHONE",
           "account_number": "ACCOUNT_NUMBER", "date_of_birth": "DATE_OF_BIRTH"}


# ---------------------------------------------------------------- inputs
def load_golden():
    with open(EVAL / "golden.csv", newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["scored"] == "yes"]


def load_manifest():
    with open(EVAL / "synthetic" / "pii_manifest.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pdf_set_hash():
    h = hashlib.sha256(b"".join(p.read_bytes() for p in sorted((EVAL / "synthetic").glob("*.pdf"))))
    return h.hexdigest()[:16]


def regenerate_pdfs():
    # --check also asserts the generated set is consistent with golden.csv
    subprocess.run([sys.executable, str(EVAL / "make_synthetic.py"), "--check"], check=True)


# ---------------------------------------------------------------- normalisers
def canon(cat):
    c = (cat or "").strip().casefold()
    for k in SENS + ["Unsafe"]:
        if c == k.casefold():
            return k
    return "Other"


def pii_norm(kind, value):
    v = str(value or "")
    if kind == "EMAIL":
        return v.strip().casefold()
    d = re.sub(r"\D", "", v)
    return d[-10:] if kind == "PHONE" else d


def pred_unsafe(r):
    """New records carry the `unsafe` field; baseline records could only say category == Unsafe."""
    return r["unsafe"] is True if "unsafe" in r else r["category"] == "Unsafe"


# ---------------------------------------------------------------- classifier harness
def build_classifier():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from backend.config import settings
    from backend.services.classifier import DocumentClassifier
    if settings.PRIMARY_LLM_MODEL != MODEL:
        sys.exit(f"effective PRIMARY_LLM_MODEL is {settings.PRIMARY_LLM_MODEL!r}, expected {MODEL!r} "
                 "(an env var or .env overrides the default); refusing to run")
    return settings, DocumentClassifier()


def arm(settings):
    """The Phase 3 switches this process runs with (docs/FEATURES.md); saved in meta.json."""
    return {"input_mode": settings.LLM_INPUT_MODE, "pii_hints": settings.PROMPT_PII_HINTS,
            "fail_closed": settings.PROMPT_FAIL_CLOSED, "wide_hs": settings.PROMPT_WIDE_HS,
            "max_tokens": settings.MAX_TOKENS}


def prompt_chars(kw):
    c = kw["messages"][0]["content"]  # a string, or content blocks when the PDF itself is attached
    return len(c) if isinstance(c, str) else sum(len(b.get("text", "")) for b in c)


def instrument(clf, calls, last, create=None):
    """Record every Anthropic call and the processed document without touching classifier code."""
    if create is None:
        orig = clf.anthropic_client.messages.create

        def create(**kw):
            t = time.perf_counter()
            r = orig(**kw)
            u = r.usage
            calls.append({"seconds": time.perf_counter() - t, "in": u.input_tokens, "out": u.output_tokens,
                          "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
                          "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                          "stop": r.stop_reason, "prompt_chars": prompt_chars(kw)})
            return r
        clf.anthropic_client.messages.create = create
    else:
        clf.anthropic_client = SimpleNamespace(messages=SimpleNamespace(create=create))
    orig_pd = clf.doc_processor.process_document

    def pd(path):
        last["content"] = orig_pd(path)
        return last["content"]
    clf.doc_processor.process_document = pd


def cost(calls):
    c = 0.0
    for k in calls:
        # `in` excludes cached tokens. claude-api skill, prompt caching: a 5-minute cache write is billed
        # at 1.25x the input rate and a cache read at 0.1x.
        cw, cr = k.get("cache_write", 0), k.get("cache_read", 0)
        ri, ro = RATE_LONG if k["in"] + cw + cr > 100_000 else RATE_SHORT
        c += (k["in"] + 1.25 * cw + 0.1 * cr) * ri + k["out"] * ro
    return c


def classify_one(clf, calls, last, row, run):
    calls.clear()
    last.clear()
    t = time.perf_counter()
    r = clf.classify_document(str(ROOT / row["file"]), use_dual_verification=False)
    total = time.perf_counter() - t
    from backend.services.classifier import quote_on_page  # the same check the classifier ships as `verified`
    pages = {p["page_number"]: p.get("text", "") for p in last.get("content", {}).get("pages", [])}
    cites = []
    for c in r.get("citations") or []:
        kind = c.get("evidence_type")
        # code = regex PII/safety context; image = a described page region; uncited = an evidence line the
        # API attached no citation to. Only "llm" citations carry a quote that can be checked on the page.
        rec = {"kind": "code" if kind in ("pii", "safety_violation") else kind if kind in ("image", "uncited")
               else "llm", "page": c.get("page_number"), "quote": (c.get("evidence_text") or "")[:200],
               "api": c.get("source") == "api"}
        if rec["kind"] in ("llm", "image"):
            pg = c.get("page_number")
            rec["page_exists"] = isinstance(pg, int) and pg in pages
        if rec["kind"] == "llm":
            rec["quote_found"] = rec["page_exists"] and quote_on_page(c.get("evidence_text"), pages[pg])
        cites.append(rec)
    pii = [{"type": d["type"], "norm": pii_norm(PII_MAP.get(d["type"], d["type"]), d["full_value"]),
            "page": d.get("page_number")} for d in (r.get("pii_results") or {}).get("detections", [])]
    # "category" holds the sensitivity level; baseline records (old output shape) may hold "Unsafe" there
    sens = r.get("sensitivity", r.get("category"))
    return {"doc_id": row["doc_id"], "run": run, "status": r.get("status"), "category": canon(sens),
            "raw_category": sens, "unsafe": r.get("unsafe"), "confidence": r.get("confidence"), "error": r.get("error"),
            "regex_unsafe": (r.get("safety_results") or {}).get("is_safe") is False,
            "reasoning": (r.get("reasoning") or "")[:300], "citations": cites, "pii": pii,
            "calls": list(calls), "cost": cost(calls), "api_seconds": sum(k["seconds"] for k in calls),
            "total_seconds": total}


# ---------------------------------------------------------------- estimate (no generation)
def cmd_estimate(args):
    if not args.skip_regen:
        regenerate_pdfs()  # synthetic PDFs are not committed; without them every synthetic doc would fail
    settings, clf = build_classifier()
    rows = load_golden()
    counter = None
    if not args.offline:
        import anthropic
        if not settings.ANTHROPIC_API_KEY:
            sys.exit("no ANTHROPIC_API_KEY in the environment; set it or pass --offline (chars/3.5 heuristic)")
        counter = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    calls, last = [], {}

    def fake_create(**kw):
        content = kw["messages"][0]["content"]
        pdf = not isinstance(content, str)
        if counter:  # the real request, minus max_tokens: schema and PDF pages are counted too
            extra = {"output_config": kw["output_config"]} if "output_config" in kw else {}
            msg = kw["messages"] if not pdf else [{"role": "user", "content": [  # cache markers are not counted
                {k: v for k, v in b.items() if k != "cache_control"} for b in content]}]
            n = counter.messages.count_tokens(model=kw["model"], messages=msg, **extra).input_tokens
        else:  # inferred. PDF support docs: 1,500-3,000 text tokens a page, plus one image per page
            n = round(prompt_chars(kw) / 3.5) + (4000 * last.get("content", {}).get("page_count", 0) if pdf else 0)
        # assume no cache hit; a block marked cache_control is billed as a 1.25x cache write
        write = pdf and any("cache_control" in b for b in content)
        calls.append({"seconds": 0, "in": 0 if write else n, "cache_write": n if write else 0, "out": 0,
                      "stop": "estimate", "prompt_chars": prompt_chars(kw)})
        body = json.dumps({"sensitivity": "Public", "unsafe": False, "confidence": 0.9, "summary": "",
                           "reasoning": "", "citations": []})
        if pdf and "output_config" not in kw:  # a citations request is answered in "field: value" lines
            body = "sensitivity: Public\nunsafe: false\nconfidence: 0.9\nsummary: s\nreasoning: r\nevidence: e"
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=body)], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=n, output_tokens=0))
    instrument(clf, calls, last, create=fake_create)
    out = []
    print(f"arm: {json.dumps(arm(settings))}")
    print(f"{'doc':7}{'calls':>6}{'prompt chars':>14}{'input tokens':>14}")
    for row in rows:
        calls.clear()
        r = clf.classify_document(str(ROOT / row["file"]), use_dual_verification=False)
        if r.get("status") != "completed" or not calls:
            sys.exit(f"{row['doc_id']}: the dry run failed ({r.get('error')}); refusing to report a partial estimate")
        tokens = sum(k["in"] + k["cache_write"] for k in calls)
        print(f"{row['doc_id']:7}{len(calls):>6}{sum(k['prompt_chars'] for k in calls):>14}{tokens:>14}")
        out.append({"doc_id": row["doc_id"], "calls": len(calls), "in": tokens, "input_cost": cost(calls),
                    "longest": max(k["in"] + k["cache_write"] for k in calls)})
    tin, calls_n, nruns = sum(o["in"] for o in out), sum(o["calls"] for o in out), args.runs
    in_cost = sum(o["input_cost"] for o in out)
    print(f"\ndocs scored: {len(rows)}; LLM calls per run: {calls_n}; "
          f"longest prompt: {max(o['longest'] for o in out)} tokens; "
          f"method: {'inferred chars/3.5 (+4000/PDF page)' if args.offline else 'count_tokens (confirmed)'}")
    print(f"input tokens per run: {tin}; x{nruns} runs = {tin * nruns}")
    costs = {k: nruns * (in_cost + calls_n * v * RATE_SHORT[1]) for k, v in OUT_TOKENS.items()}
    for k, v in OUT_TOKENS.items():
        print(f"  output assumption {k:4} ({v} tok/call): ${costs[k]:.3f}")
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / "estimate.json").write_text(json.dumps({"method": "offline" if args.offline else "count_tokens",
                                                   "arm": arm(settings), "docs": out, "runs": nruns,
                                                   "cost": costs}, indent=1))


# ---------------------------------------------------------------- run (paid)
def cmd_run(args):
    if not args.skip_regen:
        regenerate_pdfs()
    settings, clf = build_classifier()
    if not settings.ANTHROPIC_API_KEY:
        sys.exit("no ANTHROPIC_API_KEY in the environment")
    import anthropic
    rows = [r for r in load_golden() if not args.only or r["doc_id"] in args.only.split(",")]
    calls, last = [], {}
    # ride out rate limits: a failed classification is recorded as done and --resume does not retry it
    clf.anthropic_client = clf.anthropic_client.with_options(max_retries=6)
    instrument(clf, calls, last)
    RUNS.mkdir(parents=True, exist_ok=True)
    meta = {"model": settings.PRIMARY_LLM_MODEL, "sdk": anthropic.__version__, "python": sys.version.split()[0],
            "pdf_set_hash": pdf_set_hash(), "dual_verification": False, "runs": args.runs, "arm": arm(settings),
            "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    meta_path = RUNS / "meta.json"
    if list(RUNS.glob("run*.jsonl")) and not args.resume:
        # never let saved results masquerade as a fresh evaluation after code or prompt changes
        sys.exit(f"{RUNS} already holds results. Evaluate fresh with --dir <new dir>, or finish an "
                 "interrupted run of the SAME code with --resume.")
    if args.resume and meta_path.exists():
        old = json.loads(meta_path.read_text())
        diff = [k for k in ("model", "pdf_set_hash", "dual_verification", "runs", "arm") if old.get(k) != meta[k]]
        if diff:
            sys.exit(f"--resume refused: {diff} differ from {meta_path}")
    else:
        meta_path.write_text(json.dumps(meta, indent=1))
    for attempt in (1, 2):  # the second pass re-runs classifications that failed on an API outage
        outages = 0
        for run in range(1, args.runs + 1):
            path = RUNS / f"run{run}.jsonl"
            done = set()
            if path.exists():  # resumable: never pay twice for a finished doc; an outage is not a result
                recs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                keep = [r for r in recs if cause(r) != "api outage"]
                if len(keep) != len(recs):
                    path.write_text("".join(json.dumps(r) + "\n" for r in keep), encoding="utf-8")
                done = {r["doc_id"] for r in keep}
            with open(path, "a", encoding="utf-8") as f:
                for row in rows:
                    if row["doc_id"] in done:
                        continue
                    rec = classify_one(clf, calls, last, row, run)
                    outages += cause(rec) == "api outage"
                    f.write(json.dumps(rec) + "\n")
                    f.flush()
                    print(f"run{run} {row['doc_id']:6} true={row['sensitivity']:17} pred={rec['category']:17} "
                          f"{rec['status']:9} ${rec['cost']:.5f} {rec['total_seconds']:.1f}s")
        if not outages:
            break
    print(cmd_report(argparse.Namespace(out=str(RUNS / "metrics.md"))))


# ---------------------------------------------------------------- report
def cause(rec):
    """Why a classification failed. Refusals, truncations and parse failures are results of the request
    shape; an API outage (rate limit, 5xx, network) is not, so `run` retries those."""
    e = rec.get("error") or ""
    if rec.get("status") != "failed":
        return ""
    if re.search(r"Error code: (429|5\d\d)|Connection error|timed out|overloaded", e, re.I):
        return "api outage"
    return ("refusal" if "stopped with refusal" in e else "truncation" if "stopped with max_tokens" in e
            else "parse" if "no valid sensitivity" in e else "api error" if "Error code" in e else "other")


def pct(a, b):
    return "n/a" if b == 0 else f"{100 * a / b:.0f}% ({a}/{b})"


def load_records(d=None):
    recs = []
    for p in sorted(Path(d or RUNS).glob("run*.jsonl")):
        recs += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return recs


def pct_stats(xs):
    xs = sorted(xs)
    if not xs:
        return "n/a"
    p90 = xs[min(len(xs) - 1, round(0.9 * (len(xs) - 1)))]
    return f"median {statistics.median(xs):.2f}, p90 {p90:.2f}, mean {statistics.mean(xs):.2f}"


def group_section(name, rows, recs):
    ids = {r["doc_id"]: r for r in rows}
    rs = [r for r in recs if r["doc_id"] in ids]
    if not rs:
        return f"### {name}\n\nno records\n"
    nruns = len({r["run"] for r in rs})
    L = [f"### {name} ({len(ids)} docs x {nruns} runs = {len(rs)} classifications)", ""]
    cols = SENS + ["Unsafe", "Other"]
    cm = {t: Counter() for t in SENS}
    for r in rs:
        cm[ids[r["doc_id"]]["sensitivity"]][r["category"]] += 1
    L += ["Sensitivity confusion matrix (rows = golden, columns = predicted; pooled over runs). "
          "`Unsafe` = category Unsafe replaced the sensitivity (baseline output shape only), "
          "`Other` = Unknown/failed.", "",
          "| golden \\ predicted | " + " | ".join(cols) + " | recall |", "|---|" + "---|" * (len(cols) + 1)]
    for t in SENS:
        n = sum(cm[t].values())
        L.append(f"| {t} | " + " | ".join(str(cm[t][c]) for c in cols) + f" | {pct(cm[t][t], n)} |")
    nonpub = [r for r in rs if ids[r['doc_id']]['sensitivity'] != "Public"]
    fp = sum(1 for r in nonpub if r["category"] == "Public")
    hs = [r for r in rs if ids[r["doc_id"]]["sensitivity"] == "Highly Sensitive"]
    L += ["", f"- False-Public rate (Confidential or Highly Sensitive predicted Public): {pct(fp, len(nonpub))}",
          f"- Highly Sensitive predicted Public: {pct(sum(1 for r in hs if r['category'] == 'Public'), len(hs))}",
          f"- Predicted Unsafe (sensitivity not measurable for these): {sum(1 for r in rs if r['category'] == 'Unsafe')}; "
          f"failed or unparsed: {sum(1 for r in rs if r['category'] == 'Other')}"]
    per_run = []
    for run in sorted({r["run"] for r in rs}):
        rr = [r for r in rs if r["run"] == run]
        per_run.append(f"run{run}: {sum(1 for r in rr if r['category'] == ids[r['doc_id']]['sensitivity'])}/{len(rr)}")
    L.append("- Docs with the golden sensitivity, per run: " + ", ".join(per_run))
    # unsafe
    pos = {i for i, r in ids.items() if r["unsafe"] == "yes"}
    L += ["", "Unsafe detection (pooled over runs):", "",
          "| signal | precision | recall | note |", "|---|---|---|---|"]
    for label, pred, note in [("shipped output (`unsafe` field; baseline: category == Unsafe)", pred_unsafe,
                               "the LLM's decision"),
                              ("regex safety flag raised", lambda r: r["regex_unsafe"],
                               "secondary: any flag, even if not blocked")]:
        tp = sum(1 for r in rs if pred(r) and r["doc_id"] in pos)
        fpu = sum(1 for r in rs if pred(r) and r["doc_id"] not in pos)
        fn = sum(1 for r in rs if not pred(r) and r["doc_id"] in pos)
        L.append(f"| {label} | {pct(tp, tp + fpu)} | {pct(tp, tp + fn)} | {note}; positives in group: {len(pos)} |")
    # stability
    by = defaultdict(list)
    for r in rs:
        by[r["doc_id"]].append(r["category"])
    full = {d: c for d, c in by.items() if len(c) == nruns}
    stable = [d for d, c in full.items() if len(set(c)) == 1]
    L += ["", f"Label stability: {pct(len(stable), len(full))} of docs got the same category in all {nruns} runs"
          + ("" if len(stable) == len(full) else "; unstable: " +
             ", ".join(f"{d} {sorted(Counter(full[d]).items())}" for d in full if d not in stable)), ""]
    # citations
    llm = [c for r in rs for c in r["citations"] if c["kind"] == "llm"]
    kinds = Counter(c["kind"] for r in rs for c in r["citations"])
    docs_with_valid = sum(1 for r in rs if any(c.get("quote_found") for c in r["citations"] if c["kind"] == "llm"))
    comp = [r for r in rs if r["status"] == "completed"]
    L += ["Citation validity (LLM-produced citations only; code-generated PII/safety citations "
          f"[{kinds['code']}] carry redacted context and are not graded):", "",
          f"- LLM citations: {len(llm)}; cited page exists: {pct(sum(c['page_exists'] for c in llm), len(llm))}; "
          f"quote found on that page: {pct(sum(c['quote_found'] for c in llm), len(llm))}",
          f"- Completed classifications with at least one valid citation: {pct(docs_with_valid, len(comp))}"]
    if kinds["image"] or kinds["uncited"] or any(c.get("api") for c in llm):
        api = [c for c in llm if c.get("api")]
        none = sum(1 for r in comp if not any(c["kind"] in ("llm", "image") for c in r["citations"]))
        L += [f"- of which extracted by the Citations API (valid pointers by construction): {len(api)}; "
              f"their quote also matches this pipeline's page text: {pct(sum(c['quote_found'] for c in api), len(api))}",
              f"- image-region citations (described, not checkable): {kinds['image']}; "
              f"evidence lines the API attached no citation to: {kinds['uncited']}",
              f"- Completed classifications with no page citation at all: {pct(none, len(comp))}"]
    L.append("")
    # cost / latency
    calls = [k for r in rs for k in r["calls"]]
    per = lambda f: statistics.mean([sum(f(k) for k in r["calls"]) for r in rs if r["calls"]] or [0])
    L += ["Cost and latency per classification (pooled; latency includes OCR in total, API only in api):", "",
          f"- cost: mean ${statistics.mean(r['cost'] for r in rs):.5f}, max ${max(r['cost'] for r in rs):.5f}, "
          f"total ${sum(r['cost'] for r in rs):.4f}",
          f"- total seconds: {pct_stats([r['total_seconds'] for r in rs])}",
          f"- API seconds: {pct_stats([r['api_seconds'] for r in rs if r['calls']])}",
          f"- input tokens mean {statistics.mean([k['in'] for k in calls] or [0]):.0f}, "
          f"output tokens mean {statistics.mean([k['out'] for k in calls] or [0]):.0f}"]
    if len(calls) != len(rs) or any(k.get("cache_write") or k.get("cache_read") for k in calls):
        L.append(f"- per classification: {len(calls) / len(rs):.2f} API calls; tokens mean: uncached input "
                 f"{per(lambda k: k['in']):.0f}, cache write {per(lambda k: k.get('cache_write', 0)):.0f}, "
                 f"cache read {per(lambda k: k.get('cache_read', 0)):.0f}, output {per(lambda k: k['out']):.0f}")
    L += [f"- stop reasons: {dict(Counter(k['stop'] for k in calls))}", ""]
    return "\n".join(L)


def pii_section(rows, recs):
    ids = {r["doc_id"] for r in rows if r["source"] == "synthetic"}
    man = [m for m in load_manifest() if m["doc_id"] in ids]
    run1 = [r for r in recs if r["run"] == min(x["run"] for x in recs) and r["doc_id"] in ids]
    truth = defaultdict(set)   # type -> {(doc, norm, page)} real PII
    decoy = defaultdict(set)
    for m in man:
        k = (m["doc_id"], pii_norm(m["entity_type"], m["value"]), int(m["page"]))
        (truth if m["is_pii"] == "yes" else decoy)[m["entity_type"]].add(k)
    pred = defaultdict(set)
    for r in run1:
        for d in r["pii"]:
            pred[PII_MAP.get(d["type"], d["type"].upper())].add((r["doc_id"], d["norm"], d["page"]))
    L = ["### PII detection (synthetic only; the regex detector's output, run 1)", "",
         "A detection is correct when type, normalised value and page all match a manifest row with `is_pii=yes`. "
         "FP = any other detection of that type; `decoy` = it matched an `is_pii=no` row.", "",
         "| entity type | planted | TP | FN | FP | of which decoy | precision | recall |", "|---|---|---|---|---|---|---|---|"]
    tp_all = fp_all = fn_all = 0
    all_decoys = {x for d in decoy.values() for x in d}
    for ty in sorted(set(truth) | set(pred) | set(decoy)):
        t, p = truth[ty], pred[ty]
        tp, fn, fp = len(t & p), len(t - p), len(p - t)
        dc = len((p - t) & all_decoys)
        tp_all += tp; fn_all += fn; fp_all += fp
        note = " (no detector exists: recall 0 by construction)" if ty in ("PERSON", "ADDRESS") else ""
        L.append(f"| {ty}{note} | {len(t)} | {tp} | {fn} | {fp} | {dc} | {pct(tp, tp + fp)} | {pct(tp, tp + fn)} |")
    L.append(f"| **all** | {sum(len(v) for v in truth.values())} | {tp_all} | {fn_all} | {fp_all} | | "
             f"{pct(tp_all, tp_all + fp_all)} | {pct(tp_all, tp_all + fn_all)} |")
    key = lambda r: {(d["type"], d["norm"], d["page"]) for d in r["pii"]}
    same = all(key(a) == key(b) for a in run1 for b in recs if b["doc_id"] == a["doc_id"])
    L += ["", f"Detections identical across runs: {'yes' if same else 'NO (OCR or pipeline varied)'}. "
          "DRIVERS_LICENSE/PASSPORT detections have no manifest type and appear as FP rows if present.", ""]
    return "\n".join(L)


def cmd_report(args):
    recs = load_records()
    if not recs:
        sys.exit("no records in eval/runs/")
    rows = load_golden()
    meta = json.loads((RUNS / "meta.json").read_text()) if (RUNS / "meta.json").exists() else {}
    body = ["## Metrics", "", f"Run metadata: `{json.dumps(meta)}`", ""]
    body.append(group_section("TC1-TC4 (datathon test cases)", [r for r in rows if r["source"] == "test_case"], recs))
    body.append(group_section("Synthetic (24 docs)", [r for r in rows if r["source"] == "synthetic"], recs))
    body.append(pii_section(rows, recs))
    fails = [(r["doc_id"], r["run"], r["error"]) for r in recs if r["status"] != "completed" and r["category"] != "Unsafe"]
    body.append("### Failures\n\n" + ("none\n" if not fails else
                                      f"By cause: {dict(Counter(cause(r) for r in recs if cause(r)))}\n\n"
                                      + "\n".join(f"- {d} run{n}: {e}" for d, n, e in fails)))
    text = "\n".join(body)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    return text


def cmd_model_info(args):
    """PLAN Phase 3: ask the Models API what the model supports (PDF input was 'unknown today')."""
    settings, _ = build_classifier()
    import anthropic
    m = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY).models.retrieve(MODEL)
    info = {"id": m.id, "max_input_tokens": m.max_input_tokens, "max_tokens": m.max_tokens,
            "capabilities": m.capabilities}
    text = json.dumps(info, indent=1, default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o))
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / "models_api.json").write_text(text)
    print(text)


def cmd_compare(args):
    """Per-document correct runs, base dir -> this dir. PLAN gate: a win fixes >= 2 docs in all runs."""
    base, new = load_records(args.base), load_records()
    L = ["| doc | golden sensitivity | golden unsafe | sensitivity correct: base -> new | unsafe correct: base -> new |",
         "|---|---|---|---|---|"]
    for row in load_golden():
        def score(recs):
            rs = [r for r in recs if r["doc_id"] == row["doc_id"]]
            return (sum(r["category"] == row["sensitivity"] for r in rs),
                    sum(pred_unsafe(r) == (row["unsafe"] == "yes") for r in rs), len(rs))
        (bs, bu, bn), (ns, nu, nn) = score(base), score(new)

        def cell(b, n):
            tag = " **fixed**" if b < bn and n == nn else " **regressed**" if b == bn and n < nn else ""
            return f"{b}/{bn} -> {n}/{nn}{tag}"
        L.append(f"| {row['doc_id']} | {row['sensitivity']} | {row['unsafe']} | {cell(bs, ns)} | {cell(bu, nu)} |")
    text = "\n".join(L)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return text


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate"); e.add_argument("--offline", action="store_true"); e.add_argument("--runs", type=int, default=3)
    e.add_argument("--skip-regen", action="store_true"); e.add_argument("--dir")
    r = sub.add_parser("run"); r.add_argument("--runs", type=int, default=3); r.add_argument("--skip-regen", action="store_true")
    r.add_argument("--dir", help="output directory (default eval/runs; refuses if it already holds results)")
    r.add_argument("--resume", action="store_true", help="finish an interrupted run of the same code/setup")
    r.add_argument("--only", help="comma-separated doc ids (smoke test of a request shape; not a full eval)")
    sub.add_parser("model-info").add_argument("--dir")
    p = sub.add_parser("report"); p.add_argument("--out"); p.add_argument("--dir")
    c = sub.add_parser("compare"); c.add_argument("--base", default=str(RUNS)); c.add_argument("--dir")
    c.add_argument("--out")
    a = ap.parse_args()
    if a.dir:
        RUNS = Path(a.dir).resolve()
    if a.cmd in ("report", "compare"):
        print({"report": cmd_report, "compare": cmd_compare}[a.cmd](a))
    else:
        {"estimate": cmd_estimate, "run": cmd_run, "model-info": cmd_model_info}[a.cmd](a)
