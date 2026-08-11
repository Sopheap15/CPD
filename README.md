# CPD Track — Telegram Bot

A bilingual (English / Khmer) Telegram bot that lets participants look up
their Continuing Professional Development (CPD) history — training records,
CPD points, and certificate pickup status — just by sending their name.

Data lives in Excel files, so staff update it without any code.

## How it works

1. A participant opens the bot and sends their name (e.g. `/start` then `Sokha Chan`).
2. The bot finds the match (fuzzy matching; if several people share a similar
   name it shows a choice list).
3. The participant picks what to view from a menu:
   - **Summary** — total trainings, total CPD points, certificates issued / picked up / pending.
   - **Training** — list of trainings with dates, organizer, points, hours.
   - **Certificates** — certificate number, issue date, pickup status and who took it.

## Data files (in `data/`)

| File                     | Columns                                                                                                                                   |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `participants.xlsx`      | `id`, `name`, `khmer_name`, `profession`, `department`, `email`, `phone`                                                                  |
| `trainings.xlsx`         | `id`, `participant_id`, `participant_name`, `title`, `date`, `organizer`, `cpd_points`, `hours`, `status`                                 |
| `certificate_pickup.xlsx`| `id`, `participant_id`, `participant_name`, `training_title`, `certificate_number`, `issued_date`, `picked_up`, `pickup_date`, `pickup_by` |

Notes:
- Dates should be Excel date cells or text `YYYY-MM-DD`.
- `picked_up` accepts `Yes/No`, `true/false`, `1/0`, `បាន/មិនទាន់`.
- Column names are flexible — the loader maps common variations (`full_name`→`name`,
  `training_title`→`title`, etc.). Extra columns are ignored.
- **Files are auto-reloaded** when changed, so you can edit them while the bot runs.

Generate dummy data (already generated during setup):

```bash
pixi run data          # or:  ./run.sh data   (macOS/Linux)   .\run.ps1 data (Windows)
```

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

### Use Google Sheets instead of Excel (optional)

Skip step 4 — the bot can read your Google Form responses **live and directly**
(no download, no API key). Just:

1. Open each responses spreadsheet (the one the form creates) and click
   **Share → "Anyone with the link" → "Viewer"**.
2. In `.env`, set:
   ```
   GOOGLE_SHEET_ID=<the long id from the link>
   GOOGLE_SHEET_PICKUP_ID=<only if the pickup form is a separate spreadsheet>
   ```
3. That's it. The bot re-reads the sheets every few minutes (change with
   `GOOGLE_SHEET_REFRESH_MINUTES`).

Local Excel files in `data/` are still used whenever Google Sheets is not
configured.

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
.\run.ps1 data
```

Alternative: run everything through Windows Subsystem for Linux (WSL) and follow
the macOS/Linux steps above.

## Run

macOS / Linux:
```bash
./run.sh start        # foreground, Ctrl-C to stop
./run.sh stop         # stop a background bot
./run.sh status       # is it running?
```

Windows (PowerShell):
```powershell
.\run.ps1 start       # foreground, Ctrl-C to stop
.\run.ps1 stop        # stop a background bot
.\run.ps1 status      # is it running?
```

The bot runs with long-polling (no public URL needed).

## Commands

| Command | Description                                            |
| ------- | ------------------------------------------------------ |
| `/start` | Start a search (bot asks for your name)               |
| `/view Sokha Chan` | Shortcut: look up a name directly           |
| `/help` | Show help                                             |
| `/cancel` | Cancel the current search                            |

## Tests

macOS / Linux:
```bash
./run.sh test
```
Windows:
```powershell
.\run.ps1 test
```

## Project layout

```
cpd/
  bot.py          # Telegram handlers, conversation, menu
  config.py       # token + path configuration
  data_loader.py  # Excel reading, caching, auto-reload
  search.py       # fuzzy name matching
  formatter.py    # report rendering (bilingual)
  i18n.py         # all translatable strings (EN/KH)
data/             # Excel data files
pixi.toml         # environment definition (Python + libraries)
run.sh            # launcher for macOS/Linux
run.ps1           # launcher for Windows
scripts/          # dummy-data generator
tests/            # unit tests
```

## Extending

- **New languages / texts**: edit `cpd/i18n.py` — every message has an English and a
  Khmer version.
- **New Excel sheet**: add a loader in `cpd/data_loader.py` and add a menu action
  in `cpd/bot.py` + a report in `cpd/formatter.py`.
- **Move to a real database later**: replace `CpdData` in `data_loader.py` with the
  same interface (`.participants`, `.trainings_for(...)`, `.certificates_for(...)`).