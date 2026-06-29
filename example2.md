# 🎤 Demo Examples 2 — Calendar 📅 & Gmail 📧

Everything here happens **inside the chat** — no separate UI. **Type one prompt at a time**
(don't paste blocks). Each example shows the prompt, what the assistant replies, and what gets
updated behind the scenes.

> Calendar works with **no setup**. Email needs a one-time **Gmail App Password** — see
> [GMAIL_CALENDAR_SETUP.md](GMAIL_CALENDAR_SETUP.md). For the email demo, set the client's email
> (or `DEFAULT_CLIENT_EMAIL`) to **your own** address so you receive it live.

---

## 📅 A) Calendar — conflict detection (General workspace)

Stay on **General workspace**. Type these **one after another**:

**Prompt 1**
```
Schedule a court hearing today at 5pm
```
→ *📅 Noted "Court hearing" for <today>, 5:00 PM.* + an **Add to Google Calendar** link.

**Prompt 2**
```
I have a meeting with a witness today at 5pm
```
→ *⚠ Heads up — you already have "Court hearing" at 5:00 PM today, which clashes with this.
I've still noted "Meeting with a witness"…* + calendar link.

**What to say:** *"It parsed the time, checked my schedule, and warned me about the clash —
not just blindly added it."*

Other phrasings that work: *"set a client meeting on Monday at 2pm"*,
*"schedule a hearing tomorrow at 3pm"*.

---

## 📅 B) Calendar — reflected in a client's knowledge graph

Open client **Ravi Kumar** (left sidebar). Type:

```
Schedule Ravi's bail hearing on Monday at 11am
```
→ *📅 Noted "Ravi's bail hearing" for Mon …, 11:00 AM.* + calendar link.

Now open the **Knowledge Graph** tab (Ravi selected):
- A new **event node "Ravi's bail hearing"** appears, linked to a **date node "Mon …, 11:00 AM"**.
- It's also saved as a memory line: *"Scheduled: Ravi's bail hearing on Monday …"* (so future
  chats recall it).

**What to say:** *"Scheduling doesn't just hit a calendar — it becomes part of the client's case
memory and graph."*

---

## 📧 C) Gmail — email a case summary to the client

Open client **Ravi Kumar** (make sure he has an email, or `DEFAULT_CLIENT_EMAIL` is set). Type:

```
Send a mail to my client with his case details
```
→ *📧 Sent Ravi Kumar a case-summary email to <address>.*

The email body is **auto-generated** from Ravi's stored facts, status and upcoming dates
(theft case, the 5 PM contradiction, bail hearing, etc.).

You can also name the client from anywhere:
```
Email the case summary to Ravi
```

If email isn't configured yet, it replies gracefully: *"⚠ Couldn't send the email: Email not
configured…"* (so the demo never crashes).

---

## 📧 D) How the Gmail action is reflected in the knowledge base

After sending (Example C), the email is **recorded in the client's knowledge base**, not just fired off:

1. **Knowledge Graph** (Ravi) → a new **event node "Case summary email"** linked to the client and
   to the recipient address (*"sent to → <address>"*).
2. **Memory** → a recorded line: *"Case-summary email sent to Ravi Kumar (<address>) on <date>."*
   Ask afterwards:
   ```
   Have I emailed Ravi his case summary?
   ```
   → the assistant recalls that it was sent (it's in memory).
3. **Dashboard → Activity log** → a timestamped entry: *"Email sent — Ravi Kumar — Case summary → <address>"*.

**What to say:** *"Every outbound action — a scheduled date or a client email — is woven back
into that client's memory and knowledge graph, so nothing is lost and the assistant stays aware
of what's already been done."*

---

## 🔗 E) One-minute combined flow (optional)
On **Ravi Kumar**, in order:
```
Schedule Ravi's next hearing on Friday at 10am
```
```
I have another meeting on Friday at 10am
```   ← shows the clash warning
```
Send a mail to my client with his case details
```
Then open **Knowledge Graph** → see the hearing event **and** the "Case summary email" node on
Ravi's graph; open **Dashboard** → see both actions in the activity log.

---

## Troubleshooting
- **Calendar didn't trigger?** Include a scheduling word (meeting/hearing/appointment/schedule/
  remind) and a time. Pure testimony like *"Ravi said he was at the office at 5 PM"* is correctly
  **not** scheduled.
- **Email says "not configured":** set `GMAIL_ADDRESS` + `GMAIL_APP_PASSWORD` (App Password) and
  restart — see [GMAIL_CALENDAR_SETUP.md](GMAIL_CALENDAR_SETUP.md).
- **No graph node after scheduling:** make sure a **specific client** is selected (the General
  workspace stores events but has no per-client graph).
