"""Generate the synthetic eval set and eval/golden.csv. All data is fake.

    python eval/make_synthetic.py            # writes eval/synthetic/*.pdf, pii_manifest.csv, eval/golden.csv
    python eval/make_synthetic.py --check    # also verifies the output (needs pypdf)

Deterministic: fixed seed, no timestamps, Flate-compressed raw pixels for image pages.
Needs Pillow >= 10.1 (FreeType default font). Byte-identical output is only promised
for the same Python/Pillow/zlib versions.
"""
import csv
import hashlib
import html
import random
import re
import sys
import textwrap
import zipfile
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SEED = 1729
EVAL = Path(__file__).resolve().parent
ROOT = EVAL.parent
OUT = EVAL / "synthetic"
DOCX = ROOT / "HitachiDS_Datathon_Challenges_Package" / "HitachiDS_Datathon_Challenges.docx"

# ---- Rules, quoted verbatim from the docx (checked by --check) ----------------
R_HS = "Content that includes PII like SSNs, account/credit card numbers, and proprietary schematics"
R_CONF_INTERNAL = "Internal communications and business documents"
R_CONF_CUSTOMER = "customer details (names, addresses)"
R_CONF_OPS = "non-public operational content"
R_PUBLIC = "Marketing materials, product brochures, public website content, generic images."
R_UNSAFE = "should not include Hate speech, exploitative, violent, criminal, political news or cyber-threat content"

# ---- Test cases (labels from the docx; counts from the PDFs with pypdf) ----
# images = every image XObject placement per pypdf `page.images` (user decision 2026-11-13).
STUB = ("The docx 'Content Safety' line is a stub copied across all test cases (user, 2026-11-13); "
        "unsafe=no also matches the content (inferred). ")
TC = [
    ("TC1", "TC1_Sample_Public_Marketing_Document.pdf", "Public", "no", 8, 43, "yes",
     "Expected Category: Public", "Content Safety: Content is safe for the kids.",
     STUB + "Images per page 1,1,6,4,25,4,1,1 (mostly logos and icons)."),
    ("TC2", "TC2_Filled_In_Employement_Application.pdf", "Highly Sensitive", "no", 4, 3, "yes",
     "Expected Category: Highly Sensitive", "Content Safety: Content is safe for the kids.",
     STUB + "Images p1=2, p3=1 (the p3 one reuses a p1 image: 2 unique). No PII manifest for TC2."),
    ("TC3", "TC3_Sample_Internal_Memo.pdf", "Confidential", "no", 3, 0, "yes",
     "Expected Category: Confidential (Important/Internal)", "Content Safety: Content is safe for the kids.",
     STUB + "Text only."),
    ("TC4", "TC4_ Stealth_Fighter_With_Part_Names.pdf", "Confidential", "no", 18, 3, "yes",
     "Expected Category: Confidential (policy-based)", "Content Safety: Content is safe for the kids.",
     STUB + "CONFLICT: the Highly Sensitive definition names 'proprietary schematics (e.g., defense ... "
     "military equipment)', but the test-case line says Confidential; the test-case line is followed "
     "(PLAN call 2). Body is an aviation flight-ops manual template; the labelled cutaway is the p9 image "
     "(987x645), plus two banner strips on p1. Serial region (user-accepted 2026-11-13): the label "
     "'PORT SIDE F118-GE-100 TURBOFANS', top centre of the p9 image, right of 'IN-FLIGHT REFUELING "
     "RECEPTACLE'. It is an engine model designation, not a true serial number."),
    ("TC5", "TC5_Testing_Multiple_Non_Compliance_Categorization.pdf", "Confidential", "yes", 1, 7, "no",
     "Expected Category: Confidential (policy-based) and Unsafe", "Expected Category: Confidential (policy-based) and Unsafe",
     "NOT SCORED (user, 2026-11-13): the PDF does not match its docx description. It is a screen capture "
     "of a Word web editor showing page 1 of the same aviation manual as TC4; no fighter, nothing "
     "confidential or unsafe. The 7 images are toolbar strips/icons. Label kept as the docx states it, "
     "for reference only. The capture shows an account name in the toolbar."),
]

# ---- Fake-data helpers ----------------------------------------------------------
rng = random.Random(SEED)
FIRST = ["Avery", "Jordan", "Rowan", "Quinn", "Morgan", "Elliot", "Harper", "Sasha", "Devon", "Kendall", "Linden", "Marisol"]
LAST = ["Marlowe", "Quillfeather", "Brantley", "Okafor-Reyes", "Vasquez-Lind", "Tamberlane", "Hollister", "Prewitt", "Castellan", "Fairweather"]
STREET = ["Birchwood Ln", "Harbor Way", "Copperleaf Dr", "Juniper Ct", "Old Mill Rd", "Lantern St"]
CITY = [("Fernhollow", "OR"), ("Larkspur Bay", "ME"), ("Millbrook Falls", "WI"), ("Cedar Glen", "NM")]


_used_names = set()


def name():  # unique across the set, so per-entity recall never double-counts
    while (n := f"{rng.choice(FIRST)} {rng.choice(LAST)}") in _used_names:
        pass
    _used_names.add(n)
    return n


def address():
    city, st = rng.choice(CITY)
    return f"{rng.randint(10, 9899)} {rng.choice(STREET)}, {city}, {st} {rng.randint(10000, 99999)}"


def ssn():  # area 9xx is never issued as an SSN
    return f"9{rng.randint(0, 99):02d}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"


def phone():  # 555-0100..0199 is reserved for fiction
    return f"(312) 555-01{rng.randint(0, 99):02d}"


def dob():
    return f"{rng.randint(1, 12):02d}/{rng.randint(1, 28):02d}/{rng.randint(1960, 2001)}"


def acct():
    return "".join(str(rng.randint(0, 9)) for _ in range(10))


# ---- Document builder -----------------------------------------------------------
class Doc:
    def __init__(self, doc_id, slug, sensitivity, unsafe, s_quote, u_quote, notes=""):
        self.doc_id, self.slug, self.sensitivity, self.unsafe = doc_id, slug, sensitivity, unsafe
        self.s_quote, self.u_quote, self.notes = s_quote, u_quote, notes
        self.pages, self.ents = [], []

    def page(self, kind="text"):
        self.pages.append([kind, []])
        return self

    def p(self, *paras):
        self.pages[-1][1].extend(paras)
        return self

    def e(self, etype, value, is_pii="yes", note=""):
        """Record an entity on the current page and return its value for inlining."""
        self.ents.append((self.doc_id, len(self.pages), etype, value, self.pages[-1][0], is_pii, note))
        return value

    def drawing(self, boxes):
        """Image page with a box-and-label schematic: boxes = [(label, x, y, w, h)]."""
        self.pages.append(["drawing", boxes])
        return self


BIZ = "business contact; not personal PII (user-confirmed 2026-11-13)"
LOOKALIKE = "order ID shaped like an SSN; not PII"
LOREM_POLICY = ("This section restates the standard policy text. Employees must follow the handbook, complete "
                "annual training, and raise questions with their manager. ") * 3


def build():
    docs = []
    add = docs.append

    # -------- Public (7) --------
    d = Doc("SYN01", "public_brochure_contacts", "Public", "no", R_PUBLIC, R_UNSAFE,
            "Hard case: business contact details on a public brochure.")
    d.page().p("Lumenfield Solar Home Kits", "Bring clean power home in a weekend. Our plug-and-play kits include "
               "panels, a compact inverter, and a mobile app that shows your savings in real time.")
    d.page().p("Why Lumenfield?", "- 25-year panel warranty", "- Installs on most roofs and balconies",
               "- Free design consultation for every customer", "Awarded Best Home Energy Product by readers of a "
               "regional home magazine.")
    d.page().p("Talk to us", f"Email: {d.e('EMAIL', 'sales@lumenfield.example.com', 'no', BIZ)}",
               f"Phone: {d.e('PHONE', '(312) 555-0142', 'no', BIZ)}",
               f"Showroom: {d.e('ADDRESS', '400 Harbor Way, Fernhollow, OR 97001', 'no', BIZ)}",
               "Visit lumenfield.example.com to book a free consultation.")
    add(d)

    d = Doc("SYN02", "public_faq_order_ids", "Public", "no", R_PUBLIC, R_UNSAFE,
            "Hard case: SSN-shaped order IDs on public website content.")
    d.page().p("Help Center: Tracking your order", "Every purchase gets an order ID in the format NNN-NN-NNNN. "
               "You will find it in your confirmation message.",
               f"Example: Order ID {d.e('ORDER_ID', '917-42-3086', 'no', LOOKALIKE)} ships from our central warehouse.")
    d.page().p("Returns", f"To return an item, enter your order ID (for example {d.e('ORDER_ID', '904-77-1520', 'no', LOOKALIKE)}) "
               "on the returns page and print the prepaid label. Refunds post within 5 business days.")
    add(d)

    d = Doc("SYN03", "public_event_flyer_image", "Public", "no", R_PUBLIC, R_UNSAFE,
            "Image-only page 2 carries generic marketing text only (no PII).")
    d.page().p("Riverside Makers Fair", "Saturday, 10am to 6pm, Riverside Park pavilion. Free entry for all ages.")
    d.page("image").p("RIVERSIDE MAKERS FAIR", "Robots, crafts, food trucks", "Live music all afternoon",
                      "Bring the whole family!")
    d.page().p("Schedule", "10:00 Opening and kids' robot parade", "13:00 3D printing demo", "16:00 Community awards")
    add(d)

    d = Doc("SYN04", "public_press_release_political", "Public", "yes", R_PUBLIC, R_UNSAFE,
            "Unsafe at Public level: political news paragraph (fictional politician).")
    d.page().p("PRESS RELEASE: Northgate Bikes opens its third store", "Northgate Bikes today opened a new store "
               "on Lantern Street with repair classes and a kids' bike library.")
    d.page().p(f"In other news this week, State Senator "
               f"{d.e('PERSON', 'Dana Whitcombe', 'no', 'fictional public figure in news; not PII (user-confirmed 2026-11-13)')} announced a re-election campaign and "
               "attacked her opponent's tax plan during a heated televised debate, as polls show the race "
               "tightening ahead of next month's vote.",
               f"Media contact: {d.e('EMAIL', 'press@northgate.example.com', 'no', BIZ)}")
    add(d)

    d = Doc("SYN05", "public_newsletter_violent_news", "Public", "yes", R_PUBLIC, R_UNSAFE,
            "Unsafe at Public level: violent incident news item (non-graphic).")
    d.page().p("Cedar Glen Community Newsletter", "The library summer reading program starts June 3. "
               "The farmers market moves to the town square.")
    d.page().p("Police Blotter", "Police are investigating an armed robbery at a convenience store on Old Mill "
               "Road on Tuesday night. A clerk was assaulted and taken to hospital; the suspect fled with a "
               "handgun and remains at large.")
    add(d)

    d = Doc("SYN06", "public_catalog_hotline", "Public", "no", R_PUBLIC, R_UNSAFE,
            "Business hotline on the last page of a 4-page catalog.")
    d.page().p("Brightleaf Kitchen Catalog", "Cast iron, enamel, and stainless cookware for every kitchen.")
    d.page().p("Skillets", "10-inch skillet - pre-seasoned", "12-inch skillet - with helper handle")
    d.page().p("Dutch ovens", "5.5 qt enamel Dutch oven in six colors", "7 qt round oven for big batches")
    d.page().p("Questions? Our support team is here 7 days a week.",
               f"Support hotline: {d.e('PHONE', '(312) 555-0188', 'no', BIZ)}",
               f"Email: {d.e('EMAIL', 'help@brightleaf.example.com', 'no', BIZ)}")
    add(d)

    d = Doc("SYN07", "public_job_posting", "Public", "no", R_PUBLIC, R_UNSAFE,
            "Public job ad with a generic careers address.")
    d.page().p("We're hiring: Customer Success Associate", "Join a friendly team helping small businesses get the "
               "most out of our scheduling app. Hybrid role, full benefits.",
               f"Apply at {d.e('EMAIL', 'careers@tidewell.example.com', 'no', BIZ)} or visit our office at "
               f"{d.e('ADDRESS', '88 Copperleaf Dr, Millbrook Falls, WI 53001', 'no', BIZ)}.")
    add(d)

    # -------- Confidential (7) --------
    d = Doc("SYN08", "conf_internal_memo", "Confidential", "no", R_CONF_INTERNAL, R_UNSAFE,
            "Internal memo, no PII (mirrors TC3).")
    d.page().p("INTERNAL MEMO - DO NOT DISTRIBUTE", "To: Platform team   From: Engineering leadership",
               "Subject: Q3 milestones and risks", "Milestone 1: migrate billing service to the new cluster by July 15.",
               "Milestone 2: ship offline mode beta to 5% of users by August 30.")
    d.page().p("Risks", "- Vendor API deprecation may slip Milestone 1 by two weeks.",
               "- Offline sync conflicts are not yet resolved; mitigation is a server-wins policy for the beta.",
               "Budget: within the approved Q3 envelope; no new headcount.")
    add(d)

    d = Doc("SYN09", "conf_customer_list", "Confidential", "no", R_CONF_CUSTOMER, R_UNSAFE,
            "Customer names and addresses, no SSN or account numbers.")
    d.page().p("Customer shipping list - internal use only")
    for _ in range(5):
        d.p(f"{d.e('PERSON', name())} - {d.e('ADDRESS', address())}")
    add(d)

    d = Doc("SYN10", "conf_ops_runbook_lookalikes", "Confidential", "no", R_CONF_OPS, R_UNSAFE,
            "Hard case: SSN-shaped order IDs inside internal ops content; must stay Confidential, not Highly Sensitive.")
    d.page().p("Warehouse runbook - internal", "Morning shift: reconcile the overnight pick list against the WMS.")
    d.page().p("Stuck orders to re-queue today:",
               *[f"Order {d.e('ORDER_ID', ssn(), 'no', LOOKALIKE)} - carrier label failed" for _ in range(3)])
    d.page().p("Escalation: page the on-call lead if more than 20 orders are stuck for over 2 hours.")
    add(d)

    d = Doc("SYN11", "conf_meeting_notes_late_pii", "Confidential", "no", R_CONF_CUSTOMER, R_UNSAFE,
            "Hard case: the only customer details are on page 5 of 5.")
    for i in range(1, 5):
        d.page().p(f"Account review meeting notes - section {i}", "Discussed renewal timing, support ticket "
                   "trends and the onboarding backlog. Action items assigned to the account team.")
    d.page().p("Follow-up visit", f"Customer contact: {d.e('PERSON', name())}, {d.e('ADDRESS', address())}")
    add(d)

    d = Doc("SYN12", "conf_incident_report_cyber", "Confidential", "yes", R_CONF_INTERNAL, R_UNSAFE,
            "Unsafe at Confidential level: cyber-threat content (ransom note quoted in an internal report).")
    d.page().p("Security incident report - internal", "On Monday a finance workstation received a phishing email "
               "posing as an invoice update. The attachment launched ransomware.")
    d.page().p("Ransom note as recovered:", "\"Your files are encrypted. Pay 2 BTC within 48 hours or we publish "
               "your data and attack your partners next. Instructions: hxxp://invoice-update.example.test/pay\"",
               "Status: contained, host reimaged.")
    add(d)

    d = Doc("SYN13", "conf_email_scan_image_pii", "Confidential", "no", R_CONF_CUSTOMER, R_UNSAFE,
            "Hard case: customer name and address appear only inside an image-only page (p2).")
    d.page().p("Email thread printout - internal", "Re: delivery complaint. Scan of the customer's letter attached.")
    d.page("image").p("Dear Support,", "My order arrived damaged.", f"{d.e('PERSON', name())}",
                      f"{d.e('ADDRESS', address())}")
    d.page().p("Reply: replacement approved, ship by Friday.")
    add(d)

    d = Doc("SYN14", "conf_vendor_pricing_draft", "Confidential", "no", R_CONF_INTERNAL, R_UNSAFE,
            "Non-public commercial terms, no PII.")
    d.page().p("DRAFT - Vendor pricing agreement - confidential", "Unit price: $4.20 for the first 50,000 units, "
               "$3.85 thereafter. Net-45 payment terms.")
    d.page().p("Negotiation notes: walk-away price is $3.70; do not share with the vendor.")
    add(d)

    # -------- Highly Sensitive (7) --------
    d = Doc("SYN15", "hs_employment_application", "Highly Sensitive", "no", R_HS, R_UNSAFE,
            "Employment application with SSN (mirrors TC2).")
    d.page().p("Employment Application", f"Full name: {d.e('PERSON', name())}", f"Address: {d.e('ADDRESS', address())}",
               f"Phone: {d.e('PHONE', phone())}", f"Date of birth: {d.e('DATE_OF_BIRTH', dob())}",
               f"Social Security Number: {d.e('SSN', ssn())}")
    d.page().p("Work history", "2019-2024 Retail associate, Brightleaf Kitchen", "Signature: on file")
    add(d)

    d = Doc("SYN16", "hs_bank_statement", "Highly Sensitive", "no", R_HS, R_UNSAFE, "Account number.")
    d.page().p("Monthly statement", f"Account holder: {d.e('PERSON', name())}", f"{d.e('ADDRESS', address())}",
               f"Account number: {d.e('ACCOUNT_NUMBER', acct())}")
    d.page().p("Transactions", "03/02 Grocery  -84.12", "03/05 Payroll  +2,310.00", "03/09 Utilities  -120.55")
    add(d)

    d = Doc("SYN17", "hs_card_dispute_form", "Highly Sensitive", "no", R_HS, R_UNSAFE,
            "Credit card number (published test number).")
    d.page().p("Card dispute form", f"Cardholder: {d.e('PERSON', name())}",
               f"Card number: {d.e('CREDIT_CARD', '4111 1111 1111 1111', note='published test card number')}",
               "Disputed charge: $219.00 on 04/11, merchant did not deliver.")
    add(d)

    d = Doc("SYN18", "hs_hr_file_late_ssn", "Highly Sensitive", "no", R_HS, R_UNSAFE,
            "Hard case: SSN only on page 6 of 6.")
    d.page().p("Personnel file", f"Employee: {d.e('PERSON', name())}", "Department: Logistics")
    for i in range(2, 6):
        d.page().p(f"Policy acknowledgement {i - 1}", LOREM_POLICY)
    d.page().p("Payroll setup", f"SSN: {d.e('SSN', ssn())}", "Direct deposit: on file")
    add(d)

    d = Doc("SYN19", "hs_scanned_form_image_ssn", "Highly Sensitive", "no", R_HS, R_UNSAFE,
            "Hard case: name and SSN only inside an image-only page (p2); needs OCR or vision.")
    d.page().p("Scanned tax withholding form attached on the next page.")
    d.page("image").p("EMPLOYEE WITHHOLDING CERTIFICATE", f"Name: {d.e('PERSON', name())}",
                      f"SSN: {d.e('SSN', ssn())}", "Filing status: Single")
    add(d)

    d = Doc("SYN20", "hs_proprietary_schematic", "Highly Sensitive", "no", R_HS, R_UNSAFE,
            "Non-military 'proprietary schematic' (next-gen product design), chosen so the synthetic set does "
            "not contradict TC4 (military schematic labelled Confidential). Reading accepted by user 2026-11-13.")
    d.page().p("PROPRIETARY AND CONFIDENTIAL - Project Kestrel", "Next-generation solid-state battery module, "
               "revision C. Schematic on the next page. Not for release outside the hardware team.")
    d.drawing([("CELL STACK K-114", 120, 260, 420, 240), ("THERMAL PLATE TP-7", 120, 560, 420, 120),
               ("BMS BOARD B-22", 640, 260, 480, 180), ("BUS BAR SET BB-3", 640, 500, 480, 180)])
    d.page().p("Bill of materials", "K-114 cell stack x4", "TP-7 thermal plate x1", "B-22 BMS board x1")
    add(d)

    d = Doc("SYN21", "hs_fraud_case_criminal", "Highly Sensitive", "yes", R_HS, R_UNSAFE,
            "Unsafe at Highly Sensitive level: criminal content (stolen-card sale offer) with card numbers.")
    d.page().p("Fraud investigation case file", "Intercepted marketplace post, reproduced for evidence:",
               "\"Fresh stolen cards for sale, $20 each, cashout guide included:\"",
               f"{d.e('CREDIT_CARD', '5555 5555 5555 4444', note='published test card number')}",
               f"{d.e('CREDIT_CARD', '4000 0566 5566 5556', note='published test card number')}")
    d.page().p("Next steps: notify issuers, preserve logs, refer to law enforcement.")
    add(d)

    # -------- Remaining unsafe kinds, one per level (appended last so earlier docs keep their values) --------
    d = Doc("SYN22", "public_job_ad_exploitative", "Public", "yes", R_PUBLIC, R_UNSAFE,
            "Unsafe at Public level: exploitative content (forced-labour markers in a public job ad).")
    d.page().p("FACTORY JOBS ABROAD - START NEXT WEEK!", "No experience or language needed. Free travel and "
               "housing in the factory dormitory.")
    d.page().p("Terms", "- Recruitment fee of $3,000 is deducted from your wages.",
               "- The employer keeps your passport until the fee is repaid.",
               "- 14-hour shifts, 7 days a week; workers may not leave the compound.",
               f"Message our agent today: {d.e('PHONE', '(312) 555-0117', 'no', BIZ)}")
    add(d)

    # The slug keeps "conf" so the file name, and with it every saved run record, stays stable.
    d = Doc("SYN23", "conf_safeguarding_child_safety", "Highly Sensitive", "yes", R_HS, R_UNSAFE,
            "Unsafe at Highly Sensitive level: child-safety concern (grooming indicators, non-sexual) quoted in "
            "an internal school report. RELABELLED from Confidential (user, 2026-11-13, FAILURES.md F16): a "
            "minor's identity in a child-protection record counts as Highly Sensitive. This is a user decision, "
            "not a docx derivation: the quoted docx line names only SSNs, account/card numbers and schematics.")
    d.page().p("Safeguarding concern report - internal, restricted",
               f"Student: {d.e('PERSON', name())}, Year 7 (age 12)",
               f"Adult concerned: {d.e('PERSON', name())}, parent volunteer")
    d.page().p("Messages the volunteer sent the student on a gaming app:",
               "\"You're so mature for your age. Don't tell your parents we talk, it's our secret. I'll buy you "
               "a new phone if you meet me alone after school.\"",
               "Action taken: messages preserved, volunteer suspended, referred to the designated safeguarding "
               "lead and police.")
    add(d)

    d = Doc("SYN24", "hs_hr_case_hate_speech", "Highly Sensitive", "yes", R_HS, R_UNSAFE,
            "Unsafe at Highly Sensitive level: hate speech (dehumanising post about a national-origin group, "
            "no slurs) quoted in an HR case file that also holds an SSN.")
    d.page().p("HR investigation file - confidential", f"Employee: {d.e('PERSON', name())}",
               f"SSN (payroll record): {d.e('SSN', ssn())}")
    d.page().p("Complaint: the employee posted in the company chat:",
               "\"Immigrants are vermin. They don't belong in this town and we should drive every one of them out.\"",
               "Outcome: post removed, employee dismissed under the anti-harassment policy.")
    add(d)
    return docs


# ---- Minimal PDF writer (Letter, Helvetica, raw-pixel image pages) ----------------
W, H = 612, 792
IMG_W, IMG_H = 1275, 1650  # 150 dpi


def esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_stream(paras):
    lines = []
    for para in paras:
        lines += textwrap.wrap(para, 95) or [""]
        lines.append("")
    assert len(lines) <= 52, "page overflow"
    body = "".join(f"({esc(line)}) Tj T*\n" for line in lines)
    return f"BT /F1 11 Tf 14 TL 50 740 Td\n{body}ET".encode("latin-1")


def raster(kind, content):
    img = Image.new("L", (IMG_W, IMG_H), 255)
    dr = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=34)
    if kind == "drawing":
        for label, x, y, w, h in content:
            dr.rectangle([x, y, x + w, y + h], outline=0, width=4)
            dr.text((x + 16, y + 16), label, fill=0, font=font)
    else:
        y = 150
        for para in content:
            for line in textwrap.wrap(para, 55):
                dr.text((110, y), line, fill=0, font=font)
                y += 52
            y += 30
    return img


def write_pdf(path, pages):
    objs = []  # index 0 -> object 1

    def add(b):
        objs.append(b)
        return len(objs)

    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(None)  # Pages, filled below
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    kids = []
    for kind, content in pages:
        if kind == "text":
            data, res = text_stream(content), f"<< /Font << /F1 {font} 0 R >> >>"
        else:
            raw = zlib.compress(raster(kind, content).tobytes(), 9)
            im = add(f"<< /Type /XObject /Subtype /Image /Width {IMG_W} /Height {IMG_H} /ColorSpace /DeviceGray "
                     f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(raw)} >>\nstream\n".encode() + raw + b"\nendstream")
            data, res = f"q {W} 0 0 {H} 0 0 cm /Im1 Do Q".encode(), f"<< /XObject << /Im1 {im} 0 R >> >>"
        cs = add(f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream")
        kids.append(add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] /Resources {res} /Contents {cs} 0 R >>".encode()))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()

    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, b in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + b + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


# ---- Outputs ----------------------------------------------------------------------
def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    docs = build()
    golden = [(tc, f"HitachiDS_Datathon_Challenges_Package/{f}", "test_case", s, u, sc, pg, im, sq, uq, n)
              for tc, f, s, u, pg, im, sc, sq, uq, n in TC]
    ents = []
    for d in docs:
        fname = f"{d.doc_id}_{d.slug}.pdf"
        write_pdf(OUT / fname, d.pages)
        n_img = sum(k != "text" for k, _ in d.pages)
        golden.append((d.doc_id, f"eval/synthetic/{fname}", "synthetic", d.sensitivity, d.unsafe, "yes",
                       len(d.pages), n_img, d.s_quote, d.u_quote, d.notes))
        ents += d.ents
    write_csv(EVAL / "golden.csv", ["doc_id", "file", "source", "sensitivity", "unsafe", "scored", "pages", "images",
                                    "sensitivity_quote", "unsafe_quote", "notes"], golden)
    write_csv(OUT / "pii_manifest.csv", ["doc_id", "page", "entity_type", "value", "modality", "is_pii", "note"],
              [(i, p, t, v, "text" if m == "text" else "image", y, n) for i, p, t, v, m, y, n in ents])
    print(f"wrote {len(docs)} PDFs, {len(ents)} entities, {len(golden)} golden rows")
    if "--check" in sys.argv:
        check(docs)


def docx_text():
    xml = zipfile.ZipFile(DOCX).read("word/document.xml").decode("utf-8")
    paras = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)]
    return html.unescape("\n".join(paras)).replace("‑", "-")


def check(docs):
    import collections
    import pypdf  # check-only dependency

    src = docx_text()
    rows = list(csv.DictReader((EVAL / "golden.csv").open(encoding="utf-8")))
    for r in rows:
        for col in ("sensitivity_quote", "unsafe_quote"):
            assert r[col] in src, f"{r['doc_id']} {col} not in docx: {r[col]!r}"
        # strict for our own PDFs (proves the hand-written writer is valid); TC PDFs need lenient parsing
        n = len(pypdf.PdfReader(ROOT / r["file"], strict=r["source"] == "synthetic").pages)
        assert n == int(r["pages"]), f"{r['doc_id']}: {n} pages, golden says {r['pages']}"
    counts = collections.Counter(r["sensitivity"] for r in rows if r["source"] == "synthetic")
    assert all(6 <= c <= 9 for c in counts.values()) and len(counts) == 3, counts  # 9: SYN23 relabel (F16)
    texts = {d.doc_id: [p.extract_text() or "" for p in
                        pypdf.PdfReader(OUT / f"{d.doc_id}_{d.slug}.pdf").pages] for d in docs}
    keys = [(e[0], e[3]) for d in docs for e in d.ents]
    assert len(keys) == len(set(keys)), "duplicate entity value within a document"
    flat = lambda s: re.sub(r"\s+", " ", s)
    for doc_id, page, etype, value, kind, _, _ in (e for d in docs for e in d.ents):
        if kind == "text":
            assert value in flat(texts[doc_id][page - 1]), f"{doc_id} p{page} missing {value!r}"
        else:
            assert all(value not in flat(t) for t in texts[doc_id]), f"{doc_id}: image value {value!r} leaks into text"
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(OUT.glob("*.pdf")))).hexdigest()
    print(f"check OK: {len(rows)} golden rows, classes {dict(counts)}, pdf set sha256 {digest[:16]}")


if __name__ == "__main__":
    main()
