"""Populate the assistant with dummy clients, statements, calls, graphs and PDFs.

Run:  python seed_data.py        (add --reset to wipe existing data first)
"""
import os
import sys
import textwrap

import config
import memory
import rag


# --------------------------------------------------------------- tiny PDF maker
def build_pdf(path, title, paragraphs):
    """Write a minimal, valid multi-page PDF (no external deps)."""
    def esc(s):
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    # wrap into lines, paginate
    lines = [title, "=" * len(title), ""]
    for p in paragraphs:
        lines += textwrap.wrap(p, 90) or [""]
        lines.append("")
    pages = [lines[i:i + 48] for i in range(0, len(lines), 48)] or [[""]]

    objs = []  # list of raw object byte strings (without "N 0 obj")
    font_id = 3 + 2 * len(pages)
    page_ids = [3 + 2 * i for i in range(len(pages))]
    content_ids = [4 + 2 * i for i in range(len(pages))]

    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")  # obj 1
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())  # obj 2

    for i, page in enumerate(pages):
        body = "BT /F1 11 Tf 50 770 Td 14 TL\n"
        for ln in page:
            body += f"({esc(ln)}) Tj T*\n"
        body += "ET"
        body_b = body.encode("latin-1", "replace")
        page_obj = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
                    f"/Contents {content_ids[i]} 0 R >>").encode()
        content_obj = (f"<< /Length {len(body_b)} >>\nstream\n".encode()
                       + body_b + b"\nendstream")
        objs.append(page_obj)      # page id
        objs.append(content_obj)   # content id
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")  # font

    out = b"%PDF-1.4\n"
    offsets = []
    for n, raw in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + raw + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs)+1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF").encode()
    with open(path, "wb") as f:
        f.write(out)


def G(nodes, edges):
    return {"nodes": nodes, "edges": edges}


# --------------------------------------------------------------- data
CLIENTS = [
    {
        "name": "Ravi Kumar", "type": "Criminal - Theft", "status": "open",
        "summary": "Accused of office theft on 12 March. Alibi under question.",
        "statements": [
            ("In his first statement, Ravi said he was NOT at the office at 5 PM on 12 March.", "client"),
            ("Ravi stated he was at home with his brother Anil the whole evening of 12 March.", "client"),
            ("CCTV log shows the server room was accessed at 5:10 PM on 12 March.", "evidence"),
            ("In his second statement, Ravi now says he WAS at the office at 5 PM on 12 March meeting manager Suresh.", "client"),
        ],
        "graph": G(
            [{"id":"Ravi Kumar","label":"Ravi Kumar","type":"client"},
             {"id":"Office","label":"Office","type":"place"},
             {"id":"5 PM, 12 March","label":"5 PM, 12 March","type":"date"},
             {"id":"Anil","label":"Anil (brother)","type":"person"},
             {"id":"Suresh","label":"Suresh (manager)","type":"person"},
             {"id":"Theft","label":"Office Theft","type":"event"},
             {"id":"CCTV","label":"CCTV Log","type":"object"}],
            [{"source":"Ravi Kumar","target":"Theft","label":"accused of"},
             {"source":"Theft","target":"Office","label":"occurred at"},
             {"source":"Theft","target":"5 PM, 12 March","label":"at time"},
             {"source":"Ravi Kumar","target":"Anil","label":"claims alibi with"},
             {"source":"Ravi Kumar","target":"Suresh","label":"says met"},
             {"source":"CCTV","target":"Office","label":"recorded at"}]),
        "calls": [{
            "transcript": "Lawyer: Ravi, where were you at 5 PM on the 12th?\nClient: I told you, I was at home with Anil.\nLawyer: But you mentioned meeting Suresh at the office earlier.\nClient: Yes, maybe I came in briefly around five.\nLawyer: That changes the alibi. We need to be consistent.",
            "summary": "Discussed Ravi's whereabouts on 12 March. Ravi gave conflicting accounts — first home with brother Anil, then admitted being at the office around 5 PM meeting Suresh. Alibi needs reconciliation before the next hearing.",
            "action_items": ["Obtain CCTV footage timestamp from building security",
                             "Get written statement from brother Anil",
                             "Confirm meeting with manager Suresh",
                             "Reconcile the conflicting 5 PM accounts"]}],
    },
    {
        "name": "Meena Sharma", "type": "Property Dispute", "status": "solved",
        "summary": "Boundary dispute over ancestral plot in Pune. Settled out of court.",
        "statements": [
            ("Meena holds the 1998 registered sale deed for plot 47.", "evidence"),
            ("Neighbour Patil claimed 2 feet of the eastern boundary.", "opposing"),
            ("Survey by the municipal office confirmed Meena's boundary line.", "evidence")],
        "graph": G(
            [{"id":"Meena Sharma","label":"Meena Sharma","type":"client"},
             {"id":"Plot 47","label":"Plot 47, Pune","type":"place"},
             {"id":"Patil","label":"Neighbour Patil","type":"person"},
             {"id":"Sale Deed 1998","label":"Sale Deed 1998","type":"object"},
             {"id":"Survey","label":"Municipal Survey","type":"event"}],
            [{"source":"Meena Sharma","target":"Plot 47","label":"owns"},
             {"source":"Meena Sharma","target":"Sale Deed 1998","label":"holds"},
             {"source":"Patil","target":"Plot 47","label":"disputed"},
             {"source":"Survey","target":"Plot 47","label":"confirmed"}]),
        "calls": [],
    },
    {
        "name": "Arjun Verma", "type": "Divorce", "status": "in-progress",
        "summary": "Mutual-consent divorce; custody of one child and asset split pending.",
        "statements": [
            ("Arjun seeks joint custody of his 7-year-old daughter Kiara.", "client"),
            ("Both parties agreed to split the jointly-owned flat 50-50.", "agreement")],
        "graph": G(
            [{"id":"Arjun Verma","label":"Arjun Verma","type":"client"},
             {"id":"Priya","label":"Priya (spouse)","type":"person"},
             {"id":"Kiara","label":"Kiara (daughter)","type":"person"},
             {"id":"Flat","label":"Joint Flat","type":"object"}],
            [{"source":"Arjun Verma","target":"Priya","label":"divorcing"},
             {"source":"Arjun Verma","target":"Kiara","label":"seeks custody"},
             {"source":"Arjun Verma","target":"Flat","label":"co-owns"}]),
        "calls": [],
    },
    {
        "name": "Sunita Rao", "type": "Financial Fraud", "status": "unsolved",
        "summary": "Alleged investment fraud of ₹12 lakh by a chit-fund operator.",
        "statements": [
            ("Sunita invested ₹12,00,000 with operator Deepak in 2023.", "client"),
            ("Deepak's company address turned out to be fake.", "evidence")],
        "graph": G(
            [{"id":"Sunita Rao","label":"Sunita Rao","type":"client"},
             {"id":"Deepak","label":"Deepak (operator)","type":"person"},
             {"id":"Chit Fund","label":"Chit Fund Co.","type":"organization"},
             {"id":"12 Lakh","label":"₹12,00,000","type":"object"}],
            [{"source":"Sunita Rao","target":"Deepak","label":"invested via"},
             {"source":"Deepak","target":"Chit Fund","label":"runs"},
             {"source":"Sunita Rao","target":"12 Lakh","label":"lost"}]),
        "calls": [],
    },
    {
        "name": "Imran Khan", "type": "Contract Breach", "status": "closed",
        "summary": "Vendor failed to deliver IT equipment; resolved with refund.",
        "statements": [
            ("Vendor TechNova missed the delivery deadline of 1 Jan 2024.", "evidence"),
            ("A full refund of ₹4,50,000 was issued after mediation.", "agreement")],
        "graph": G(
            [{"id":"Imran Khan","label":"Imran Khan","type":"client"},
             {"id":"TechNova","label":"TechNova Pvt Ltd","type":"organization"},
             {"id":"Contract","label":"Supply Contract","type":"object"}],
            [{"source":"Imran Khan","target":"TechNova","label":"contracted"},
             {"source":"TechNova","target":"Contract","label":"breached"}]),
        "calls": [],
    },
    {
        "name": "Aisha Kapoor", "type": "Family - Custody", "status": "open",
        "summary": "Dispute over custody and school attendance across two cities.",
        "statements": [
            ("Aisha says her daughter was with her in Bengaluru on 12 Oct.", "client"),
            ("School attendance record shows the child in Mumbai on 12 Oct.", "evidence"),
        ],
        "graph": G(
            [{"id":"Aisha Kapoor","label":"Aisha Kapoor","type":"client"},
             {"id":"Daughter","label":"Daughter","type":"person"},
             {"id":"Bengaluru","label":"Bengaluru","type":"place"},
             {"id":"Mumbai","label":"Mumbai","type":"place"}],
            [{"source":"Aisha Kapoor","target":"Daughter","label":"parent of"},
             {"source":"Daughter","target":"Bengaluru","label":"claimed at"}]),
        "calls": [],
    },
    {
        "name": "Nikhil Rao", "type": "Vendor Dispute", "status": "in-progress",
        "summary": "Supplier failure to deliver goods; unpaid invoice dispute.",
        "statements": [
            ("Nikhil: TechSupplies delivered defective units on 01 Mar and invoice remains unpaid.", "client"),
        ],
        "graph": G([
            {"id":"Nikhil Rao","label":"Nikhil Rao","type":"client"},
            {"id":"TechSupplies","label":"TechSupplies Pvt Ltd","type":"organization"}],
            [{"source":"Nikhil Rao","target":"TechSupplies","label":"claims against"}]),
        "calls": [],
    },
    {
        "name": "Sara Menon", "type": "Product Liability", "status": "open",
        "summary": "Alleged defective battery caused device fire; seeking damages.",
        "statements": [
            ("Sara: The battery supplied by TechSupplies overheated on 05 Apr.", "client"),
        ],
        "graph": G([
            {"id":"Sara Menon","label":"Sara Menon","type":"client"},
            {"id":"TechSupplies","label":"TechSupplies Pvt Ltd","type":"organization"}],
            [{"source":"Sara Menon","target":"TechSupplies","label":"supplier"}]),
        "calls": [],
    },
    {
        "name": "Diego Alvarez", "type": "Commercial - Contract", "status": "in-progress",
        "summary": "Dispute over delayed delivery and contract penalties.",
        "statements": [
            ("Diego: Supplier must deliver within 30 days of PO; penalty after 45 days.", "client"),
        ],
        "graph": G([
            {"id":"Diego Alvarez","label":"Diego Alvarez","type":"client"},
            {"id":"Supplier","label":"Supplier","type":"organization"}],
            [{"source":"Diego Alvarez","target":"Supplier","label":"contract with"}]),
        "calls": [],
    },
    {
        "name": "Maya Iyer", "type": "Commercial - Compliance", "status": "open",
        "summary": "Multi-party negotiation with specific deliverables and certificates.",
        "statements": [
            ("Maya: Vendor must produce compliance certificate by next Tuesday.", "client"),
        ],
        "graph": G([
            {"id":"Maya Iyer","label":"Maya Iyer","type":"client"},
            {"id":"Vendor","label":"Vendor","type":"organization"}],
            [{"source":"Maya Iyer","target":"Vendor","label":"negotiating with"}]),
        "calls": [],
    },
    {
        "name": "Dr. Kavya Nair", "type": "Intellectual Property", "status": "open",
        "summary": "Provisional disclosure of an algorithm and related technical notes.",
        "statements": [
            ("Kavya: Filed a provisional disclosure on 02 Feb for a two-stage encoder.", "client"),
        ],
        "graph": G([
            {"id":"Dr. Kavya Nair","label":"Dr. Kavya Nair","type":"client"},
            {"id":"Algorithm","label":"Two-stage encoder","type":"object"}],
            [{"source":"Dr. Kavya Nair","target":"Algorithm","label":"disclosed"}]),
        "calls": [],
    },
    {
        "name": "Vikram Gupta", "type": "Corporate Fraud & Asset Tracing", "status": "open",
        "summary": "Allegations of embezzlement using layered shell companies and rapid fund movements.",
        "statements": [
            ("Whistleblower: Funds were routed through ShellCo LLP to offshore accounts on 15 Feb.", "witness"),
            ("Accounting: Unexplained vendor payments to entities controlled by Vikram.", "evidence"),
        ],
        "graph": G([
            {"id":"Vikram Gupta","label":"Vikram Gupta","type":"client"},
            {"id":"ShellCo","label":"ShellCo LLP","type":"organization"},
            {"id":"OffshoreBank","label":"Offshore Bank","type":"organization"},
            {"id":"Forensic","label":"Forensic Report","type":"object"}],
            [{"source":"Vikram Gupta","target":"ShellCo","label":"linked to"},
             {"source":"ShellCo","target":"OffshoreBank","label":"transferred to"},
             {"source":"Forensic","target":"ShellCo","label":"investigates"}]),
        "calls": [{
            "transcript": "Forensic Analyst: We saw rapid transfers on 15-16 Feb into multiple jurisdictions.\nLawyer: Can you provide a trace?\nAnalyst: Yes, we have SWIFT chain logs and beneficiary names.",
            "summary": "Forensic analyst briefing on money-movement chain; potential freezing actions recommended.",
            "action_items": ["Request SWIFT extracts from bank", "File provisional asset-freeze motion", "Serve discovery on ShellCo"]
        }],
    },
    {
        "name": "Mass Tort Group A", "type": "Mass Tort - Toxic Exposure", "status": "in-progress",
        "summary": "Multiple claimants alleging long-term exposure to Contaminant X at industrial plant.",
        "statements": [
            ("Plaintiff A: Chronic respiratory issues since 2019 after work at Plant Z.", "client"),
            ("Plaintiff B: Hospital records show elevated exposure markers.", "evidence"),
        ],
        "graph": G([
            {"id":"Group A","label":"Group A Plaintiffs","type":"group"},
            {"id":"Plant Z","label":"Plant Z","type":"place"},
            {"id":"Contaminant X","label":"Contaminant X","type":"object"},
            {"id":"Manufacturer","label":"Manufacturer","type":"organization"}],
            [{"source":"Group A","target":"Plant Z","label":"worked at"},
             {"source":"Plant Z","target":"Contaminant X","label":"exposed to"},
             {"source":"Contaminant X","target":"Manufacturer","label":"produced by"}]),
        "calls": [],
    },
    {
        "name": "Hannah Lee", "type": "Cross-border IP & Hosting Dispute", "status": "open",
        "summary": "Source-code leak and copyrighted material hosted on offshore servers; takedown and injunctive relief sought.",
        "statements": [
            ("Hannah: Proprietary modules were copied and published on mirror.example.com on 02 Mar.", "client"),
            ("Hosting provider logs show file uploads from an IP range associated with MirrorCo.", "evidence"),
        ],
        "graph": G([
            {"id":"Hannah Lee","label":"Hannah Lee","type":"client"},
            {"id":"MirrorCo","label":"MirrorCo","type":"organization"},
            {"id":"MirrorHost","label":"mirror.example.com","type":"object"}],
            [{"source":"Hannah Lee","target":"MirrorHost","label":"copyrighted content on"},
             {"source":"MirrorCo","target":"MirrorHost","label":"operates"}]),
        "calls": [],
    },
    {
        "name": "Environmental Trust", "type": "Regulatory Enforcement", "status": "open",
        "summary": "Alleged illegal discharge into river; requires expert hydrogeology and satellite imagery analysis.",
        "statements": [
            ("Trust: Satellite images show discoloration downstream from Plant Y on 10 Jun.", "evidence"),
            ("Regulator: Sample tests show contaminant levels above statutory limits.", "evidence"),
        ],
        "graph": G([
            {"id":"Environmental Trust","label":"Environmental Trust","type":"organization"},
            {"id":"Plant Y","label":"Plant Y","type":"place"},
            {"id":"Satellite","label":"Satellite Imagery","type":"object"},
            {"id":"HydroReport","label":"Hydrogeology Report","type":"object"}],
            [{"source":"Environmental Trust","target":"Plant Y","label":"complains about"},
             {"source":"Satellite","target":"Plant Y","label":"shows"},
             {"source":"HydroReport","target":"Satellite","label":"corroborates"}]),
        "calls": [],
    },
]

SAMPLE_PDFS = [
    ("witness_statement_ravi.pdf", "Witness Statement — State vs. Ravi Kumar", [
        "Case No. CR-2024-0912. Statement recorded at Shivajinagar Police Station.",
        "The complainant alleges that on 12 March 2024, office property and a laptop were "
        "stolen from the third-floor server room between 5:00 PM and 5:30 PM.",
        "Witness Suresh Patel, the office manager, states that he briefly saw the accused, "
        "Ravi Kumar, near the third floor at approximately 5:05 PM on the said date.",
        "The accused, Ravi Kumar, in his initial statement denied being present at the office "
        "at 5 PM and claimed he was at his residence with his brother, Anil Kumar.",
        "CCTV access logs retrieved from the building security system indicate that an access "
        "card registered to Ravi Kumar was used to enter the server room at 5:10 PM.",
        "The investigating officer notes a discrepancy between the accused's stated whereabouts "
        "and the documentary CCTV evidence which requires further clarification.",
    ]),
    ("property_deed_meena.pdf", "Memorandum — Sharma Property Dispute", [
        "Subject: Boundary dispute concerning Plot No. 47, Kothrud, Pune.",
        "Ms. Meena Sharma is the registered owner of Plot No. 47 by virtue of a sale deed "
        "registered in 1998 (Doc No. 4471/1998).",
        "The adjoining owner, Mr. Patil, asserted an encroachment claim over approximately two "
        "feet along the eastern boundary.",
        "A demarcation survey conducted by the municipal survey office confirmed that the "
        "boundary wall stands within Ms. Sharma's legally registered limits.",
        "The matter was settled amicably; Mr. Patil withdrew the encroachment claim and the "
        "case is recorded as resolved.",
    ]),
]


def run(reset=False):
    if reset:
        if os.path.exists(config.STORE_FILE):
            os.remove(config.STORE_FILE)
            print("[seed] store reset")
        # Physically remove the vector DB — robust even if ChromaDB is corrupted.
        import shutil
        if os.path.isdir(config.CHROMA_DB_PATH):
            shutil.rmtree(config.CHROMA_DB_PATH, ignore_errors=True)
            print("[seed] vector store removed (rebuilds fresh)")
    memory._STORE = None  # force reload

    for c in CLIENTS:
        client = memory.create_client(c["name"], c["type"], c["status"], c["summary"])
        cid = client["id"]
        # graph (manual, rich)
        memory._STORE["graphs"][cid] = c["graph"]
        memory._save()
        # statements (with embeddings so semantic recall + contradiction work)
        for text, speaker in c["statements"]:
            memory.add_statement(cid, text, speaker=speaker, source="seed")
        # calls
        for call in c["calls"]:
            memory.add_call(cid, call["transcript"], call["summary"], call["action_items"])
        memory.log_activity(cid, "Case seeded", c["type"])
        print(f"[seed] {c['name']} ({c['status']})")

    # contradiction demo: run the detector on Ravi's conflicting statements
    ravi = next((cl for cl in memory.list_clients() if cl["name"] == "Ravi Kumar"), None)
    if ravi:
        sts = memory.get_statements(ravi["id"])
        last = sts[-1]  # "...now says he WAS at the office..."
        try:
            found = memory.check_contradictions(ravi["id"], last["text"], new_id=last["id"])
            print(f"[seed] Ravi contradiction check -> {len(found)} found")
        except Exception as e:  # noqa: BLE001
            print(f"[seed] contradiction check skipped: {e}")

    # PDFs -> generate + ingest into RAG
    for fname, title, paras in SAMPLE_PDFS:
        path = os.path.join(config.UPLOAD_DIR, fname)
        build_pdf(path, title, paras)
        cid = "general"
        if "ravi" in fname:
            cid = next((cl["id"] for cl in memory.list_clients() if cl["name"] == "Ravi Kumar"), "general")
        if "meena" in fname:
            cid = next((cl["id"] for cl in memory.list_clients() if cl["name"] == "Meena Sharma"), "general")
        try:
            n = rag.ingest_pdf(path, fname, client_id=cid)
            memory.log_activity(cid, "Document uploaded", f"{fname} ({n} chunks)")
            print(f"[seed] indexed {fname} -> {n} chunks")
        except Exception as e:  # noqa: BLE001
            print(f"[seed] PDF ingest skipped ({fname}): {e}")

    print("\nDone. Start the server with:  python app.py   then open http://127.0.0.1:8000")


if __name__ == "__main__":
    run(reset="--reset" in sys.argv)
