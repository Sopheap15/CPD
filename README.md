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
   - If the course has a fee, the bot generates a **Bakong KHQR** payment code
     (fee from the `fee` column in `courses.xlsx`, in USD). The participant
     scans it with the Bakong app and the bot **confirms the payment
     automatically** by polling Bakong. After payment, registration is saved to
     `data/in_bot_registrations.csv` and the participant gets a **Join course
     group** button so they can join the course's Telegram group (see "Course
     groups" below).
   - **📊 View CPD History** — the bot asks for their name.
2. For View CPD, the bot finds the match (fuzzy matching; if several people
   share a similar name it shows a choice list).
3. The participant picks what to view from a menu:
   - **Summary** — total trainings, total CPD points, certificates issued / picked up / pending.
   - **Training** — list of trainings with dates, organizer, points, hours.
   - **Certificates** — certificate number, issue date, pickup status and who took it.

Both the registration list and every CPD report end with a professional contact
note (CPD officer phone/Telegram).

## Data files (in `data/`)

| File                     | Purpose                                                                                                        |
| ------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `Transformed_Course_Registrations_with_Certificates.xlsx` | Master registration + certificate workbook (the main source). |
| `courses.xlsx`           | Open courses shown on the "Register for Course" button (`Course ID`, `Title`, `Date`, `CPD Points`, `fee`, `status`, optional `Link` = fallback group invite link). |
| `course_groups.json`     | Maps each course to its Telegram group chat (managed via the `/admin_group` command — do not edit by hand). |
| `in_bot_registrations.csv` | Registrations made through the bot; merged into the data automatically. Copy them into the master workbook later. |
| `telegram_links.json`    | Maps Telegram account IDs to participant names (used to recognize returning participants). |
| `participants.xlsx` / `trainings.xlsx` / `certificate_pickup.xlsx` | Optional simple-format files (used only if the master workbook is absent). |

Notes:
- Dates should be Excel date cells or text `YYYY-MM-DD`.
- **Files are auto-reloaded** when changed, so you can edit them while the bot runs.

Generate dummy data (already generated during setup):

```bash
pixi run data
```

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

## Payments (Bakong KHQR)

Registration fees are paid by scanning a KHQR code with the **Bakong** app:

1. Fill in the Bakong merchant settings in `.env`:
   - `BAKONG_ACCOUNT_ID` — your merchant account, e.g. `merchant@aclb`
   - `BAKONG_MERCHANT_NAME` — fallback name; the QR shows the **course title**
     (max 25 chars) when a course has one
   - `BAKONG_TOKEN` — a developer token from
     https://api-bakong.nbc.gov.kh/register
   - `BAKONG_EMAIL` — the email you registered with on the Bakong developer
     portal. When set, the bot **renews its own token** automatically (see
     "Token renewal" below) and you never paste one in again.
   - `BAKONG_CURRENCY=USD` (fees are stored in USD in `courses.xlsx`)
2. When a participant registers for a paid course, the bot sends a **dynamic
   KHQR image** with the exact fee and a unique bill number.
3. The bot **polls Bakong** (`check_transaction_by_md5`) every 20 seconds and
   confirms the registration automatically the moment the payment lands. A
   participant can also tap **"I have paid / Check payment"** to check early.
4. Unpaid registrations are stored in `in_bot_registrations.csv` with
   `payment_status = Pending` so the admin can see outstanding fees; confirmed
   ones become `Paid`.
5. A course with a fee always triggers the payment step, even before the
   developer token arrives: the QR code is shown and the participant taps
   **"I have paid"**, which marks the registration `Unverified` and notifies
   the admin to confirm it manually (`/admin_confirm <bill>`). Once the token
   is set, confirmation is fully automatic.
6. If no `BAKONG_ACCOUNT_ID` is present, registrations are saved without
   payment and the admin can collect fees manually.

### Token renewal

Bakong Open API tokens are valid for ~90 days. To stop manually pasting new
tokens from the portal:

1. Set `BAKONG_EMAIL` in `.env` to the email you registered with on
   https://api-bakong.nbc.gov.kh/register.
2. The bot checks the token shortly after startup and again every
   `BAKONG_TOKEN_RENEW_DAYS` (default 24) days. If the token is missing or
   expires within that window it calls `POST /v1/renew_token`, applies the new
   token in memory, and writes it back into `.env` (so it survives restarts).
3. You can also renew on demand:
   `pixi run python scripts/renew_bakong_token.py`

Bakong only accepts requests from Cambodian IP addresses — run the bot on a
server/VPS located in Cambodia for payments (and token renewal) to work.

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

# 4. Put your real Excel files in data/ (or generate sample data)
pixi run data
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

# 4. Put your real Excel files in data/ (or generate sample data)
pixi run data
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
Start-Process -FilePath "pixi" -ArgumentList "run","start" -WorkingDirectory "C:\Users\osopheap\Desktop\CPD_track"
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
| `.\run.ps1 export`    | Rebuild `worker/data.json` from the Excel files           |
| `.\run.ps1 test-worker` | Run the Cloudflare Worker logic tests                   |
| `.\run.ps1 lint`      | Compile-check all Python files                            |
| `pixi run start`      | Same as `run.ps1 start` (foreground)                      |

## Tests

The main verification is the Worker logic test (search + report formatting):

macOS / Linux:
```bash
./run.sh test-worker
```
Windows:
```powershell
.\run.ps1 test-worker
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
  bot.py           # Telegram handlers, conversation, menu, in-bot registration + payment flow
  config.py        # token + path + Bakong configuration
  data_loader.py   # Excel reading, caching, auto-reload, registration merge
  registrations.py # in-bot course registration storage (CSV, incl. payment fields)
  payments.py      # Bakong KHQR generation + payment verification
  course_groups.py # course -> Telegram group mapping (course_groups.json)
  search.py        # fuzzy name matching
  formatter.py     # report rendering (bilingual)
  real_data.py     # parses the master "Transformed ... with Certificates" workbook
  i18n.py          # all translatable strings (EN/KH)
  storage.py       # Telegram-ID <-> participant-name links
data/              # Excel data files + in_bot_registrations.csv + telegram_links.json
worker/            # Cloudflare Worker port (entry.py, data.json, wrangler.jsonc)
scripts/           # export_data.py, test_worker_logic.py, generate_dummy_data.py
pixi.toml          # environment definition (Python + libraries)
run.sh             # launcher for macOS/Linux
run.ps1            # launcher for Windows
```

## Extending

- **New languages / texts**: edit `cpd/i18n.py` — every message has an English and a
  Khmer version.
- **New Excel sheet**: add a loader in `cpd/data_loader.py` and add a menu action
  in `cpd/bot.py` + a report in `cpd/formatter.py`.
- **Move to a real database later**: replace `CpdData` in `data_loader.py` with the
  same interface (`.participants`, `.trainings_for(...)`, `.certificates_for(...)`).