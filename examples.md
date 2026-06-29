# 🎤 Lexora — Complex Demo Scenarios

Copy-paste scripts to present the project. Each example lists **what to do**, the **exact text
to type/say**, and **what the judges will see**.

> **Before you start:** `py -3.11 seed_data.py --reset` (server stopped) → `py -3.11 app.py` →
> open the app and hard-refresh (Ctrl+Shift+R). Use Chrome/Edge.

---

## 1 — Multijurisdictional custody + evidence timeline (complex fact pattern)

**Goal:** demonstrate timeline extraction, RAG over PDFs, and contradiction detection across
multiple statements about dates/times.

**Setup:** Select any client or create a new one (e.g. **Aisha Kapoor**).

**Do this** — send these messages in order:
```
Aisha: My daughter was with me in Bengaluru on 12 Oct at 14:00.
```
```
Later: I received a written school attendance record showing she was in Mumbai on 12 Oct.
```
```
Upload a school attendance PDF that indicates dates for October (use Documents tab).
```

**What the judges see:**
- A retrieved snippet from the uploaded PDF under the assistant's answer (RAG pill).
- A contradiction or timeline conflict is surfaced when the system detects two overlapping
  location/time claims for the same child.
- The knowledge graph links the child, locations (Bengaluru, Mumbai), and documents.

**Why this is powerful:** family-law matters often hinge on dates and places; Lexora builds
an evidence timeline and flags mismatched testimony versus documentary records.

---

## 2 — Cross-case liability: supplier fraud connecting multiple clients

**Goal:** show how the same corporate counterparty links distinct client matters and
exposes systemic risk across the firm's caseload.

**Setup:** Create two clients: **Nikhil Rao** (vendor dispute) and **Sara Menon** (product liability).

**Do this** — for Nikhil, type:
```
Nikhil: TechSupplies Pvt Ltd delivered defective power units on 01 Mar; invoice unpaid.
```
For Sara, type:
```
Sara: TechSupplies supplied the battery that overheated on 05 Apr; they refused replacement.
```

**What the judges see:**
- Both client graphs show `TechSupplies Pvt Ltd` as a shared node.
- The dashboard or a client search will surface both matters, revealing a pattern.

**Why this is powerful:** the firm can detect repeat offenders and coordinate discovery
over multiple matters quickly.

---

## 3 — Contract complex clause extraction + calendar commitments

**Goal:** extract contractual obligations from a typed clause, create calendar reminders,
and surface action items.

**Setup:** Create client **Diego Alvarez** and paste a contract clause into chat:
```
Diego: Clause 7.2 — Supplier shall deliver 30 days after receipt of PO; penalty applies
if not delivered within 45 days; service review scheduled on 01 Jul.
```

**Do this** — then ask:
```
Create reminders for delivery deadlines and a calendar invite for the service review.
```

**What the judges see:**
- Lexora extracts dates/times and adds events to the app calendar (GCal link provided).
- Action items: `Monitor delivery by <date>`, `Send penalty notice if delayed`.
- The knowledge graph contains the contract as an `event` linked to the supplier and client.

**Why this is powerful:** turns dense contractual language into operational tasks and
calendar events automatically.

---

## 4 — Complex call with multi-party action items (live or recorded)

**Goal:** transcribe a multi-speaker negotiation, extract action items and follow-ups per party.

**Setup:** Use Voice Call or Live Call. If testing manually, simulate persons by toggling
speaker roles in the UI. Use client **Maya Iyer**.

**Script (short):**
```
Lawyer: We need the vendor to produce the compliance certificate by next Tuesday.
Vendor rep: We'll send it, but only after we receive the pending payment within 3 days.
Client: I'll arrange the payment and confirm by email tomorrow.
```

**What the judges see:**
- A meeting summary and a list of action items attributed to the right party:
  - Vendor: `Send compliance certificate by <date>`
  - Client: `Arrange payment and confirm by <date>`
- Each agreed follow-up becomes an item in the client's memory and activity log.

**Why this is powerful:** captures operational commitments in multi-party calls and reduces
miscommunication risk.

---

## 5 — Intellectual property quick triage (complex technical facts)

**Goal:** show RAG plus knowledge-graph extraction on technical text (patent fragments,
disclosure notes) and create a case stub.

**Setup:** Create client **Dr. Kavya Nair** and paste a short patent paragraph or upload a PDF.

**Do this** — type:
```
Kavya: The algorithm uses a two-stage encoder and a novel attention mask to prioritise
feature X; I filed a provisional disclosure on 02 Feb.
```

**What the judges see:**
- The assistant extracts `algorithm`, `feature X`, `provisional disclosure` as entities and
  links them in the graph.
- The dashboard shows a new open matter; the activity log records the disclosure date.

**Why this is powerful:** helps tech‑heavy practice areas capture scaffolded technical facts
and build evidentiary trails quickly.

---

## Quick tips for presenters
- Emphasise that Lexora is offline‑first: local LLM + local embeddings; optional remote key only
  if you explicitly add `GEMINI_API_KEY`.
- Use the Documents tab to demo RAG with any PDF.
- For live demos, prefer Chrome/Edge for speech recognition.

---

If you'd like, I can also regenerate `seed_data.py` to create demo clients matching these
names (Aisha Kapoor, Nikhil Rao, Sara Menon, Diego Alvarez, Maya Iyer, Dr. Kavya Nair). Let
me know and I will update the seeder accordingly.
