# CPD Track — Telegram Bot

A bilingual (English / Khmer) Telegram bot that lets participants look up
their Continuing Professional Development (CPD) history — training records,
CPD points, and certificate pickup status — just by sending their name.

Data lives in Excel files, so staff update it without any code.

## How it works

1. A participant opens the bot (`/start`) and is asked to choose:
   - **📋 Register for Course** — shows the available courses (with date, CPD
     points and fee) and lets the participant pick one. Returning participants
     (Telegram already linked to their record, or whose license number is on
     file) are registered without re-entering their details; new participants
     are asked for license, name, phone and location.
   - If the course has a fee, the bot asks the participant to pay by scanning
     the **ABA QR code** (`aba.png`) and upload a photo of the receipt. The bot
     **verifies the receipt automatically** with local OCR (Tesseract) — it
     checks that the recipient name/account and the expected fee appear on the
     receipt — then saves the registration to `data/in_bot_registrations.csv`
     with a random `payment_ref` number for easy lookup. The participant then
     gets a **Join course group** button so they can join the course's Telegram
     group (see "Course groups" below).
   - **📊 View CPD History** — the bot asks for their name.
2. For View CPD, the bot finds the match (fuzzy matching; if several people
   share a similar name it shows a choice list).
3. The participant picks what to view from a menu:
   - **Summary** — total trainings, total CPD points, certificates issued / picked up / pending.
   - **Training** — list of trainings with dates, organizer, points, hours.
   - **Certificates** — certificate number, issue date, pickup status and who took it.

Both the registration list and every CPD report end with a professional contact
note (CPD officer phone/Telegram).

## Quick start (deploy & run)

The bot is a normal Python app you run on any machine (PC, laptop, VPS).
It uses long-polling — **no public URL or web server is needed** to run it.

### 1. Install pixi (once) and clone the repo

Windows:
```powershell
irm https://pixi.sh/install.ps1 | iex
git clone git@github.com:Sopheap15/CPD.git
cd CPD
```

macOS / Linux:
```bash
curl -fsSL https://pixi.sh/install.sh | bash
git clone git@github.com:Sopheap15/CPD.git
cd CPD
```

### 2. Create your bot token

Message **@BotFather** on Telegram → `/newbot` → copy the token
(it looks like `123456789:AA...`). Keep it private.

### 3. Create your `.env`

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and at minimum set:
```
TELEGRAM_BOT_TOKEN=123456789:AAAyour_bot_token_here
```

(Optional) If your internet provider blocks Telegram directly, route the bot
through a **Cloudflare Worker** (you write ~10 lines of JavaScript in
[Cloudflare Workers](https://workers.cloudflare.com) — see "Cloudflare Worker
proxy" below). If you have one, uncomment and set:
```
TELEGRAM_API_BASE_URL=https://your-worker.yourname.workers.dev/bot
```

### 4. Install everything you need (once)

```powershell
pixi install
```

### 5. Put your real Excel files in `data/`

Drop your courses + registration workbooks into the `data/` folder. Files
auto-reload when changed, so you can edit them while the bot runs.

### 6. Run the bot

Windows (foreground, Ctrl-C to stop):
```powershell
.\run.ps1 start
```

Windows (background — keeps running after you close the terminal):
```powershell
Start-Process -FilePath "pixi" -ArgumentList "run","start" -WorkingDirectory "C:\Users\osopheap\Desktop\CPD"
```

macOS / Linux:
```bash
nohup ./run.sh start > data/cpd.out 2> data/cpd.err &
```

You should see logs ending with `Application started` — your bot is now online.

### Run two bots at once (e.g. CPD + Clerkship)

Each project is fully self-contained in its own folder with its own `.env` and
its own `.pixi` environment. Just start each one in its own directory:

```powershell
cd C:\Users\osopheap\Desktop\CPD
Start-Process -FilePath "pixi" -ArgumentList "run","start" -WorkingDirectory "C:\Users\osopheap\Desktop\CPD"

cd C:\Users\osopheap\Desktop\Clerkship_bot
Start-Process -FilePath "pixi" -ArgumentList "run","start" -WorkingDirectory "C:\Users\osopheap\Desktop\Clerkship_bot"
```

They run side-by-side without conflicting.

## Cloudflare Worker (Telegram API proxy)

If your network blocks `api.telegram.org` directly (common on some ISPs — you
get `httpx.ConnectError` on startup), route the bot through a free Cloudflare
Worker instead:

1. Go to [workers.cloudflare.com](https://workers.cloudflare.com) → create a
   Worker.
2. Paste this code and **Deploy**:

```javascript
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/") {
      return new Response("CPD Track bot Telegram API proxy. Use /bot<token>/<method>", { status: 200 });
    }
    url.protocol = "https:";
    url.host = "api.telegram.org";
    return fetch(new Request(url.toString(), request));
  },
};
```

3. Your Worker now has a URL like
   `https://cpdtracking.yourname.workers.dev`.
4. In `.env`, set:
   ```
   TELEGRAM_API_BASE_URL=https://cpdtracking.yourname.workers.dev/bot
   ```
   (note the `/bot` suffix — the bot appends its token to it automatically).
5. Restart the bot:
   ```powershell
   .\run.ps1 stop
   .\run.ps1 start
   ```

To confirm it works, the bot should log `Application started` instead of
`ConnectError`. You can also check older projects already using this approach
(e.g. `run.ps1` in `C:\Users\osopheap\Desktop\CPD`).

## Troubleshooting connection errors

- **`httpx.ConnectError` on startup** → your network can't reach
  `api.telegram.org`. Either wait/change network, or add the Cloudflare Worker
  proxy above.
- **`Application started` but the bot doesn't reply** → make sure the token in
  `.env` matches the one @BotFather gave you.
- **`InvalidURL: Invalid port: ...`** → the `.env` file is malformed. Replace it
  with a clean copy of `.env.example` and re-enter your values.

## Data files (in `data/`)

| File                     | Purpose                                                                                                        |
| ------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `Transformed_Course_Registrations_with_Certificates.xlsx` | Master registration + certificate workbook (the main source). |
| `courses.xlsx`           | Open courses shown on the "Register for Course" button (`Course ID`, `Title`, `Date`, `CPD Points`, `fee`, `status`, optional `Link` = fallback group invite link). |
| `course_groups.json`     | Maps each course to its Telegram group chat (managed via the `/admin_group` command — do not edit by hand). |
| `in_bot_registrations.csv` | Registrations made through the bot (created at runtime; includes `payment_ref` for searching). |
| `telegram_links.json`    | Maps Telegram account IDs to participant names (created at runtime, used to recognize returning participants). |
| `participants.xlsx` / `trainings.xlsx` / `certificate_pickup.xlsx` | Optional simple-format files (used only if the master workbook is absent). |

Notes:
- Dates should be Excel date cells or text `YYYY-MM-DD`.
- **Files are auto-reloaded** when changed, so you can edit them while the bot runs.

## Course groups

Telegram **bots cannot create groups or add members**. To give participants a
group for each course:

1. An admin creates one Telegram group per course and **names it with the
   course date + title** (e.g. `2026-08-24 Role of pharmacy in hospital`).
2. Add the bot as an **administrator** of the group (needed so the bot can
   generate invite links).
3. The admin runs the bot command **inside that group**:

   ```
   /admin_group <Course ID>
   ```

   The bot stores the mapping in `data/course_groups.json`.

4. When a participant registers for that course, the bot creates a fresh invite
   link and sends them a **Join course group** button. If the group isn't set
   up, the bot falls back to the `Link` column in `courses.xlsx` (a static
   invite link), then to a "contact the admin" message.

A participant can only join via the link they receive — the bot cannot put them
in the group automatically.

## Payments (ABA receipt verification)

Registration fees are paid by scanning the **ABA QR code** (`aba.png` in the
project root) with the ABA Mobile app, then uploading the receipt to the bot:

1. Fill in your ABA details in `.env`:
   - `ABA_MERCHANT_NAME` — the recipient name shown on the receipt (e.g.
     `SOPHEAP OENG`)
   - `ABA_ACCOUNT_NUMBER` — the ABA account number (fallback check for direct
     bank-transfer receipts)
2. When a participant registers for a paid course, the bot sends the ABA QR
   image with the exact fee (from the `fee` column in `courses.xlsx`, in USD).
3. The participant scans it, pays, then taps **"I have paid"** and uploads a
   screenshot of the receipt.
4. The bot **verifies the receipt locally with OCR** (Tesseract):
   - the recipient name or account number appears on the receipt, and
   - the expected fee amount appears as an actual monetary value.
   If both match, the registration is saved to `in_bot_registrations.csv` with
   `status = Paid` and a random 10-digit `payment_ref` number for easy lookup.
   If the receipt can't be verified, the registration is stored as
   `status = Unverified` and the admin confirms it manually
   (`/admin_confirm <bill>`).
5. A course with a fee always triggers the payment step. If no `ABA_MERCHANT_NAME`
   is set, registrations are saved without payment and fees are collected manually.

Requirements: **Tesseract OCR** must be installed on the machine running the
bot (see `pixi.toml` — `pytesseract`, `opencv`, `pyzbar` are included in the
pixi environment).

## Admin commands

| Command                       | Description                                                        |
| ----------------------------- | ------------------------------------------------------------------ |
| `/admin`                      | Show the full admin command menu                                    |
| `/admin_group <Course ID>`    | (in a group) link this group to a course                            |
| `/admin_group_clear <Course ID>` | Unlink a course's group                                          |
| `/admin_group_rename <Course ID> <title>` | Rename a course's group (bot must be group admin)   |
| `/admin_groups`               | List course ↔ group chat IDs                                        |
| `/admin_setup`                | One-tap buttons that link/create a group for each open course       |
| `/admin_regs`                 | List all in-bot registrations (incl. pending fees)                  |
| `/admin_reg_del <id> <course>`| Delete a single registration                                        |
| `/admin_reg_clear yes`        | Delete ALL in-bot registrations                                     |
| `/admin_confirm <bill>`       | Mark a manual/unverified payment as Paid                            |
| `/admin_kick <Course ID> <telegram_id>` | Remove a member from a course group                    |
| `/admin_list`                 | List all Telegram↔participant links                                 |
| `/admin_link <ID> <Name>`     | Manually link a Telegram ID to a participant                        |
| `/admin_unlink <ID or Name>`  | Remove a link                                                       |
| `/admin_view <Name>`          | View any participant's CPD history                                  |

## Setup (macOS / Linux)

Requirements: [pixi](https://pixi.sh) only — everything else is handled by it.

```bash
# 1. Install pixi (once)
curl -fsSL https://pixi.sh/install.sh | bash

# 2. Create a bot with @BotFather and put its token in .env
cp .env.example .env
#   then edit .env and set TELEGRAM_BOT_TOKEN=...

# 3. Install the environment (downloads Python + libraries)
pixi install

# 4. Put your real Excel files in data/
```

## Setup (Windows)

```powershell
# 1. Install pixi (once, in PowerShell)
irm https://pixi.sh/install.ps1 | iex
#    close and reopen the terminal afterwards

# 2. Create a bot with @BotFather and put its token in .env
Copy-Item .env.example .env
#   then edit .env and set TELEGRAM_BOT_TOKEN=...

# 3. Install the environment
pixi install

# 4. Put your real Excel files in data/
```

Alternative: run everything through Windows Subsystem for Linux (WSL) and follow
the macOS/Linux steps above.

## Run

### Start / stop / status

macOS / Linux:
```bash
./run.sh start        # foreground, Ctrl-C to stop
./run.sh stop         # stop a running bot
./run.sh status       # is it running?
```

Windows (PowerShell):
```powershell
.\run.ps1 start       # foreground, Ctrl-C to stop
.\run.ps1 stop        # stop a running bot
.\run.ps1 status      # is it running?
```

`stop` and `status` only act on **this** project's bot — they match the bot by
its pixi python path, so they won't touch the Clerkship bot or other python
processes.

### Run in the background (keeps running after you close the terminal)

Windows (PowerShell):
```powershell
Start-Process -FilePath "pixi" -ArgumentList "run","start" -WorkingDirectory "C:\Users\osopheap\Desktop\CPD"
```

macOS / Linux:
```bash
nohup ./run.sh start > data/cpd.out 2> data/cpd.err &
```

The bot runs with long-polling (no public URL needed).

### Other helper commands

Windows (PowerShell) / macOS-Linux (`run.ps1` / `run.sh`):

| Command               | What it does                                              |
| --------------------- | --------------------------------------------------------- |
| `.\run.ps1 lint`      | Compile-check all Python files                            |
| `pixi run start`      | Same as `run.ps1 start` (foreground)                      |

## Tests

Run a compile check across every Python file:

macOS / Linux:
```bash
./run.sh lint
```
Windows:
```powershell
.\run.ps1 lint
```

## Commands

| Command | Description                                            |
| ------- | ------------------------------------------------------ |
| `/start` | Show the Register / View CPD menu                     |
| `/view Sokha Chan` | Shortcut: view CPD for a name directly. |
| `/help` | Show help                                             |
| `/cancel` | Cancel the current search                            |
| `/admin_group <Course ID>` | (admin, in a group) link this group to a course |

`/admin_group` must be run by an admin **inside** the course's Telegram group.
All other admin commands are listed under "Admin commands" above.

## Project layout

```
cpd/
  bot.py           # application assembly, conversation wiring, background jobs
  config.py        # token + path + payment configuration
  constants.py     # shared conversation-state constants
  i18n.py          # all translatable strings (EN/KH)
  handlers/        # Telegram conversation handlers
    start.py       #   /start entry point + main-menu callbacks
    history.py     #   CPD history lookup + report menus
    registration.py#   course registration + ABA receipt payment flow
    groups.py      #   course-group invite links + admin setup nudges
    admin.py       #   admin-only commands
    common.py      #   shared helpers (keyboards, data access, replies)
  services/        # business logic (no telegram imports)
    data_loader.py #   Excel reading, caching, auto-reload, registration merge
    registrations.py # in-bot course registration storage (CSV, incl. payment fields)
    payments.py    #   pending-payment tracking
    receipt_scanner.py # OCR receipt verification (recipient + amount checks)
    course_groups.py # course -> Telegram group mapping (course_groups.json)
    search.py      #   fuzzy name matching
    formatter.py   #   report rendering (bilingual)
    real_data.py   #   parses the master "Transformed ... with Certificates" workbook
    storage.py     #   Telegram-ID <-> participant-name links
data/              # Excel data files (+ runtime in_bot_registrations.csv, telegram_links.json)
pixi.toml          # environment definition (Python + libraries)
run.sh             # launcher for macOS/Linux
run.ps1            # launcher for Windows
```

## Extending

- **New languages / texts**: edit `cpd/i18n.py` — every message has an English and a
  Khmer version.
- **New Excel sheet**: add a loader in `cpd/services/data_loader.py`, add a menu
  action in `cpd/handlers/history.py` and a report in `cpd/services/formatter.py`.
- **Move to a real database later**: replace `CpdData` in `data_loader.py` with the
  same interface (`.participants`, `.trainings_for(...)`, `.certificates_for(...)`).