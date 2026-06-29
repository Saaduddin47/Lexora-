# 📧 Email + 📅 Calendar — How it works & setup

Both features live **inside the chat** (no separate UI). You just type naturally.

---

## 📅 Calendar (conflict detection + scheduling)

Type a scheduling sentence in any chat (General workspace or a client):

- *"I have a meet at 5pm"*
- *"Schedule a court hearing tomorrow at 3pm"*
- *"Set a client meeting on Monday at 2pm"*

What happens automatically:
1. It parses the **date & time** from your sentence.
2. It **checks your existing events for a clash** and warns you, e.g.
   *"⚠ Heads up — you already have 'Court hearing' on Sun 14 Jun, 5:00 PM, which clashes with this."*
3. It saves the event **into the app** and — for a client — into that client's **memory + knowledge graph** (an event node linked to its date).
4. The reply includes a **➕ Add to Google Calendar** link (one click puts it on your real calendar).

**No setup needed** — this works out of the box. Testimony sentences like *"Ravi said he was
at the office at 5 PM"* are correctly ignored (not treated as scheduling).

> The "Add to Google Calendar" link is the no-setup way to mark it on Google. If you want the
> event written to Google Calendar **automatically** (no click), that requires Google OAuth
> (Calendar API) — ask and I'll wire it; for a demo the one-click link is simpler and reliable.

---

## 📧 Email a case summary to a client

Type in a client's chat (or name them):

- *"Send a mail to my client with his case details"*
- *"Email the case summary to Ravi"*

It will **summarise the client's case** (facts, status, upcoming dates) and **email it** to the
client's address. The reply confirms: *"📧 Sent Ravi a case-summary email to …"*.

### One-time setup (Gmail App Password)
Gmail blocks normal-password logins, so use an **App Password** (free):

1. Turn on **2-Step Verification** on your Google account.
2. Go to **Google Account → Security → App passwords**, create one for "Mail", copy the 16-character code.

**Easiest — a `.env` file** in the project root (the app loads it automatically; no VS Code
setting needed). Create `HackPrix/.env`:
```
GMAIL_ADDRESS=youraddress@gmail.com
GMAIL_APP_PASSWORD=the16charapppassword
DEFAULT_CLIENT_EMAIL=youraddress@gmail.com
```
Then **restart the server** (`python app.py`). That's it.

> The app reads `.env` itself, so you can ignore VS Code's "terminal environment injection is
> disabled / python.terminal.useEnvFile" notice.

**Alternative — shell env vars** (instead of `.env`):
```powershell
$env:GMAIL_ADDRESS      = "youraddress@gmail.com"
$env:GMAIL_APP_PASSWORD = "the16charapppassword"   # no spaces
$env:DEFAULT_CLIENT_EMAIL = "youraddress@gmail.com"
python app.py
```

### Per-client email
- When you create a client, fill in the **Client email** field (added to the New Client form).
- Recipient priority: the client's email → `DEFAULT_CLIENT_EMAIL` → `GMAIL_ADDRESS`.
- **Demo tip:** set the client's email (or `DEFAULT_CLIENT_EMAIL`) to **your own** address so you
  receive the "client" email and can show it to the judges.

---

## Quick demo line
> In **General workspace**: type *"Schedule a court hearing today at 5pm"*, then *"I have a meet
> at 5pm"* → it warns about the clash and gives the Google Calendar link.
> In **Ravi Kumar**: type *"Send a mail to my client with his case details"* → he gets the summary email.

## Files added
- `calendarx.py` — NL date parsing, conflict logic, Google Calendar link.
- `mailer.py` — Gmail SMTP sending.
- `chat.py` — detects calendar/email intent and routes it (before normal chat).
- `memory.py` — events store + per-client memory/graph reflection; client `email` field.
