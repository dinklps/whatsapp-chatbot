# WhatsApp intake assistant (conveyancing)

An inbound WhatsApp bot that does first-line intake for conveyancing enquiries. It asks one
question at a time, in the caller's language, to find out:

- who is messaging (purchaser, lawyer, bank, other), their name and firm/bank
- which project and unit the enquiry concerns
- what they need, classified into the call-log reason categories

It then alerts the person in charge (PIC) of that project on WhatsApp and gives the caller the
PIC's WhatsApp link. Complaints go to the head of department instead. Every enquiry is saved as a
call-log row. Returning callers are recognised by number and are not asked who they are again.

The bot never answers case questions itself (status, amounts, bank accounts, legal advice).

## How it works

```
WhatsApp -> Meta Cloud API -> POST /webhook (FastAPI) -> Engine -> SQLite
                                                           |-> Claude: extract answers, word the next question
                                                           |-> config/projects.json: who is the PIC
                                                           '-> WhatsApp: reply to caller, alert to PIC
```

The engine (`app/engine/engine.py`) decides which question comes next (`app/engine/slots.py`).
Claude only extracts what the caller said and words that one question. If Claude's reply asks
about something else, or contains more than one question, it is re-worded or replaced with fixed
wording (`app/engine/templates.py`). If Claude is unreachable the bot keeps working with the
fixed wording in English, Malay or Chinese.

## Setup

Requires Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env      # then fill in .env
```

### 1. Project and staff list

Edit `config/projects.json` (it ships with placeholders):

- `staff`: each person's name, WhatsApp number (digits with country code, e.g. `60123456789`),
  email and office number
- `projects`: each project's name, `aliases` (other spellings callers use), location, and the
  staff ids of its `pic` and `hod`
- `default_pic`: who gets enquiries for projects not in the list
- `default_hod`: who gets complaints when the project is unknown or has no `hod`

Restart the server after editing.

### 2. Claude

Put an Anthropic API key in `.env` as `ANTHROPIC_API_KEY`.

### 3. WhatsApp (Meta Cloud API)

1. In Meta for Developers, create a Business app, add the WhatsApp product and register the
   bot's phone number.
2. Fill `.env`: `WHATSAPP_ACCESS_TOKEN` (a permanent system-user token), `WHATSAPP_PHONE_NUMBER_ID`,
   `WHATSAPP_APP_SECRET`, and a `WHATSAPP_VERIFY_TOKEN` of your choosing.
3. In the app's WhatsApp > Configuration, set the webhook URL to `https://<your-host>/webhook`,
   enter the same verify token, and subscribe to the `messages` field.
4. Create the staff alert template in WhatsApp Manager > Message templates. Meta must approve it
   before the bot can message staff who haven't written to the bot in the last 24 hours.

   - Name: `intake_alert`, Category: Utility, Language: English (`en`)
   - Body:

     ```
     New conveyancing enquiry
     Caller type: {{1}}
     Caller: {{2}}
     Project: {{3}}
     Unit: {{4}}
     Reason: {{5}}
     Summary: {{6}}
     Reply to caller: {{7}}
     ```

5. Set `DRY_RUN=false` in `.env`. While `DRY_RUN=true`, outgoing messages are printed instead of sent.

## Running

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For local testing with a real phone, expose the port with a tunnel (e.g.
`cloudflared tunnel --url http://localhost:8000`) and use the tunnel URL as the webhook URL.

Run a single server process: the per-caller message ordering is kept in memory.

## Trying it without WhatsApp

```powershell
.\.venv\Scripts\python.exe -m scripts.chat
.\.venv\Scripts\python.exe -m scripts.chat --phone 60123456789   # a different caller
```

Needs the Anthropic key. Uses its own database (`data/chat.db`). Staff alerts are printed.

## Call log

```powershell
.\.venv\Scripts\python.exe -m scripts.export                    # today
.\.venv\Scripts\python.exe -m scripts.export --date 2026-11-19
.\.venv\Scripts\python.exe -m scripts.export --all
```

Writes `exports/call-log-<date>.csv` with date, time, caller number, caller type, name, firm/bank,
project, unit, location, reason, summary, who it was transferred to, and status.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The tests use a scripted stand-in for Claude, so they need no keys.

## Moving to PostgreSQL

Install a driver (`pip install "psycopg[binary]"`) and set
`DATABASE_URL=postgresql+psycopg://user:password@host/dbname`. Tables are created on start-up.

## Data and privacy

Callers' numbers and messages are stored in the database (`data/` by default, not committed).
Keep `.env` and the database out of version control and restrict access to the host.
