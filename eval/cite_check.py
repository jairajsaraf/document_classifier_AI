"""Supplementary: strict vs punctuation-insensitive quote matching on text-layer pages (run 1). Run in the image: python eval/cite_check.py"""
import json,re,sys,PyPDF2,glob,csv

gold={r["doc_id"]:r for r in csv.DictReader(open("eval/golden.csv",encoding="utf-8"))}
al=lambda s: re.sub(r"[^a-z0-9]","",(s or "").casefold())
recs=[json.loads(l) for l in open("eval/runs/run1.jsonl",encoding="utf-8")]
tot=strict=lenient=0; samples=[]; per={}
for r in recs:
    pdf=gold[r["doc_id"]]["file"]
    pages=[p.extract_text() or "" for p in PyPDF2.PdfReader(pdf).pages]
    for c in r["citations"]:
        if c["kind"]!="llm" or not c.get("page_exists"): continue
        txt=pages[c["page"]-1]
        # OCR pages have empty PyPDF2 text; skip those for lenient check
        if not txt.strip(): continue
        tot+=1; strict+=bool(c["quote_found"])
        ok=all(al(s) in al(txt) for s in re.split(r"\.\.\.|…",c["quote"]) if al(s))
        lenient+=ok
        k="TC" if r["doc_id"].startswith("TC") else "SYN"; a=per.setdefault(k,[0,0,0]); a[0]+=1;a[1]+=bool(c["quote_found"]);a[2]+=ok
        if not ok and len(samples)<6 and r["doc_id"].startswith("TC"): samples.append((r["doc_id"],c["page"],c["quote"][:110]))
print("text-layer citations",tot,"strict",strict,"alnum-only lenient",lenient, per)
for s in samples: print(s)
