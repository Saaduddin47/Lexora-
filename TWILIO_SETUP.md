# ☎ Phone Line — Real Two-Phone Calls over Twilio

Lawyer (you) and client (your friend) are on **two different phones in two different
locations**. You dial your Twilio number; Twilio bridges the call to your friend and streams
the **live transcription of both sides** to Lexora, which commits it to memory + the
knowledge graph in real time and auto-creates the client. Only the phone audio touches Twilio;
all the AI (memory, graph, contradictions, summary) stays local.

```
Your phone ──call──▶ Twilio number ──/voice (TwiML)──▶ <Dial> ──▶ Friend's phone
                          │
                          └─ <Transcription> ──POST──▶ ngrok ──▶ /transcription ──▶ memory + graph
```

---

## 0. You need
- A Twilio account + a **voice-capable phone number** (you have a US number ✅)
- **ngrok** installed ✅
- The friend's phone number in **E.164** format, e.g. `+14155551234`
- ⚠ **Trial accounts:** Twilio trial can only `<Dial>` **verified** numbers. Verify your
  friend's number first: Twilio Console → *Phone Numbers → Verified Caller IDs → Add*. (Or
  upgrade the account.) Inbound calls to your Twilio number work on trial.

---

## 1. Start ngrok pointing at your server's port
Your server runs on port **1000** (from your `app.py`). In a terminal:
```powershell
ngrok http 1000
```
Copy the HTTPS forwarding URL it prints, e.g. `https://abc123.ngrok-free.app`.

## 2. Start Lexora with the Twilio settings
In a **new** terminal (server stopped), set the three env vars and run:
```powershell
$env:TWILIO_NUMBER        = "+1XXXXXXXXXX"      # your Twilio number
$env:TWILIO_CLIENT_NUMBER = "+1FRIENDNUMBER"    # friend's phone to dial (verified if trial)
$env:PUBLIC_URL           = "https://abc123.ngrok-free.app"   # the ngrok URL from step 1
py -3.11 app.py
```
> Tip: leave a client **unselected** so the call auto-creates a fresh client from the name.

## 3. Point your Twilio number at the webhook
Twilio Console → **Phone Numbers → Manage → Active numbers → (your number) → Voice Configuration**:
- **"A call comes in"** → **Webhook**
- URL: `https://abc123.ngrok-free.app/voice`
- Method: **HTTP POST**
- **Save**.

(Real-Time Transcription is driven by the TwiML we return — no extra console toggle needed.
If your account reports transcription isn't enabled, enable *Voice Intelligence / Real-Time
Transcription* in the console.)

## 4. Run the demo
1. On the laptop, open the app → **☎ Phone Line** tab (it shows "Ready. Call your Twilio number…").
2. From **your phone**, call your **Twilio number**.
3. Twilio answers and **dials your friend**; she picks up — now you're connected on two phones.
4. Talk. The transcript streams into the **☎ Phone Line** tab live; the client is auto-created,
   the knowledge graph grows, and contradictions are flagged.
5. Hang up → a **meeting summary + action items** appear, saved to the client.

---

## Demo script (small)
Leave the client unselected; keep the two "scene" lines parallel so the contradiction fires.

> **You (📞):** "Good morning, am I speaking with you about your case?"
> **Friend (📱):** "Yes, my name is **Karan Malhotra** and I need help with a **criminal case about an assault**."
> *(→ client "Karan Malhotra", type Criminal, auto-created)*
> **You:** "Where were you on the 3rd of May?"
> **Friend:** "I was **present at the scene on the 3rd of May at 8 PM**."
> **You:** "Are you certain?"
> **Friend:** "Actually, I was **not present at the scene on the 3rd of May**."
> *(→ ⚠ contradiction flagged live)*
> **You:** "Okay, please **send me your ID proof by Friday** and I will **prepare the bail application**."
> *(hang up → summary + action items)*

---

## Troubleshooting
- **No transcript appears:** confirm `PUBLIC_URL` exactly matches the current ngrok URL (it
  changes every `ngrok` restart) **and that you restarted the server after setting it**. The
  webhook URL in Twilio must use the **same** ngrok host.
- **Call connects but doesn't dial the friend:** check `TWILIO_CLIENT_NUMBER` is E.164
  (`+1…`) and (on trial) **verified**.
- **Twilio error "application error":** open the ngrok inspector at `http://127.0.0.1:4040`
  to see the exact request/response to `/voice`.
- **Friend doesn't get the call (trial):** verify her number or upgrade the account.
- **Contradiction didn't fire:** keep the two statements parallel and flip only the
  affirm/deny word ("was present" → "was **not** present").
- The Phone Line view polls every ~1.5 s, so transcript lines appear a moment after they're spoken.

---

## What was added (code)
- `telephony.py` — TwiML, an ordered async worker that commits each utterance via the same
  `chat.live_turn` pipeline (auto-create + contradiction + graph), and end-of-call summary.
- `app.py` — routes `POST /voice`, `POST /transcription`, `POST /voice/status`,
  `GET /api/telephony/live`.
- `config.py` — `TWILIO_NUMBER`, `TWILIO_CLIENT_NUMBER`, `PUBLIC_URL`, `TRANSCRIBE_LANG`.
- Frontend — the **☎ Phone Line** tab that shows the live transcript, detected client,
  contradictions, and the post-call summary.

This is independent of the browser **📱 Live Call** demo, which is unchanged.
