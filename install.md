# CPD Track Bot — Installation & Configuration Guide (Windows)

Step-by-step instructions to set up and run the bot on a new Windows computer.
Follow the steps in order. You only do steps 1–6 once; after that you just run
the bot (step 7).

---

## Requirements

| Requirement | Why |
|---|---|
| Windows 10/11 | Operating system |
| Internet access | Bot talks to Telegram |
| A Telegram bot token | From @BotFather (see step 5) |

The bot uses **long polling** — no public IP, no web server, no port
forwarding is needed.

---

## Step 1 — Install Git

Open **PowerShell** (Start → type `powershell` → Enter) and run:

```powershell
winget install --id Git.Git -e
```

Close and reopen PowerShell so `git` is available. Verify:

```powershell
git --version
```

> If `winget` is not available, download Git from <https://git-scm.com/download/win>
> and install with the default options.

---

## Step 2 — Install pixi (Python environment manager)

In PowerShell:

```powershell
irm https://pixi.sh/install.ps1 | iex
```

Close and reopen PowerShell. Verify:

```powershell
pixi --version
```

pixi will automatically install the correct Python version and all libraries —
you never install Python manually.

---

## Step 3 — Get the project code

```powershell
cd $HOME\Desktop
git clone https://github.com/Sopheap15/CPD.git
cd CPD
```

If you want the branch with the newest fixes:

```powershell
git checkout feat/certificate-pickup-flow
```

(Otherwise you are on `main`, which is fine once the fixes are merged.)

---

## Step 4 — Install everything (one command)

```powershell
.\run.ps1 install
```

This does two things:

1. **`pixi install`** — downloads Python 3.12 and all dependencies
   (python-telegram-bot, pandas, openpyxl, OpenCV, pytesseract, …).
2. **Installs Tesseract OCR** via winget if missing. Tesseract reads the
   uploaded payment receipts — **the bot will start without it, but every
   receipt check will fail**, so make sure this step succeeds.

Verify Tesseract afterwards:

```powershell
Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

This must print `True`.

> **Manual Tesseract install** (only if winget failed):
> download from <https://github.com/UB-Mannheim/tesseract/wiki> and install to
> the default location `C:\Program Files\Tesseract-OCR`. The bot finds it there
> automatically — nothing to configure.

---

## Step 5 — Create and configure `.env`

Copy the template and open it:

```powershell
Copy-Item .env.example .env
notepad .env
```

Edit the values:

### Required

```ini
# Token from @BotFather (Telegram). To keep the SAME bot as the old computer,
# copy the exact token from the old machine's .env file.
TELEGRAM_BOT_TOKEN=123456789:AA...your_token...

# Your Telegram numeric ID (comma-separated for multiple admins).
# Don't know it? Message the bot /myid once it runs, or use @userinfobot.
ADMIN_IDS=123456789
```

### Required for receipt verification

```ini
# Name printed under "To Account" on KHQR receipts:
ABA_MERCHANT_NAME=SOPHEAP OENG

# Account number fallback (direct bank-transfer receipts):
ABA_ACCOUNT_NUMBER=002370133
```

### Optional

| Variable | When to set it |
|---|---|
| `TELEGRAM_API_BASE_URL=https://your-worker.workers.dev/bot` | Your internet provider blocks Telegram → route through a Cloudflare Worker |
| `TELEGRAM_PROXY=http://host:port` | Alternative proxy option |
| `CPD_DATA_DIR=` | Only if you keep Excel files somewhere else |

Save and close Notepad.

> ⚠️ **One bot = one computer.** Two machines running the same token at the
> same time will conflict (both poll Telegram). Stop the old machine's bot
> (`.\run.ps1 stop`) before starting here.

---

## Step 6 — Put the data files in `data\`

Some files come with the clone; others exist only on the old computer because
they contain personal data and are excluded from git.

### Already included by `git clone` ✅

| File | Purpose |
|---|---|
| `data\courses.xlsx` | Course list (fees, dates, CPD points, certificate status, group links) |

> ℹ️ **About `Transformed_Course_Registrations_with_Certificates.xlsx`:**
> it also ships with the clone, and it is the bot's **master data source** for
> participants/trainings/certificates (`cpd/services/real_data.py`) — keep it.
> If View-CPD suddenly shows nobody, this file is missing — put it back.

### Copy from the old computer 📁 (not in git)

Copy these into the project's `data\` folder:

| File | Why |
|---|---|
| `data\Transformed_Course_Registrations_with_Certificates.xlsx` | Master participant/training/certificate records (**if** you use this data mode) |
| `data\in_bot_registrations.csv` | All in-bot registrations and certificate pickups |
| `data\telegram_links.json` | Which Telegram account is linked to which participant |
| `data\used_receipts.json` | Receipt anti-replay list — **copy it, otherwise an old receipt photo could be accepted again** |
| any other `.xlsx` workbooks you keep there | e.g. updated master exports |

Easiest way — from the OLD computer:

```powershell
# run inside the OLD project folder
robocopy data \\NEWPC\shared-folder\data /E *.csv *.json *.xlsx
# then copy .env too
Copy-Item .env \\NEWPC\shared-folder\
```

(or use a USB stick — the files are small).

---

## Step 7 — Run the bot

```powershell
.\run.ps1 start
```

* First time: Windows may ask to allow Python through the firewall → **Allow**.
* Stop: press `Ctrl-C` (or `.\run.ps1 stop` from another terminal).
* Check whether it runs: `.\run.ps1 status`.
* Test it: message the bot on Telegram → `/start` → try **View CPD History**
  and a test registration.

### Useful commands

| Command | Action |
|---|---|
| `.\run.ps1 start` | Start the bot (foreground) |
| `.\run.ps1 stop` | Stop a running bot |
| `.\run.ps1 status` | Show running/not running |
| `.\run.ps1 lint` | Syntax-check all Python files |
| `.\run.ps1 shell` | Open a shell inside the Python environment |
| `.\run.ps1 install` | Re-install environment (after dependency changes) |

---

## Updating later

To get the latest code:

```powershell
git pull
.\run.ps1 stop
.\run.ps1 start
```

Excel files in `data\` can be edited while the bot runs — changes reload
automatically, no restart needed.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `pixi: command not found` | Close and reopen PowerShell after installing pixi |
| Receipt check always fails | Tesseract missing → repeat step 4; verify with `Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe"` |
| Receipt check says "យូរពេក" (too slow) | Photo too large/dark — send a direct screenshot instead of a camera photo |
| Bot doesn't respond at all | Wrong token, no internet, or Telegram blocked → set `TELEGRAM_API_BASE_URL` (Cloudflare Worker) |
| `401 Unauthorized` in the log | Invalid/expired bot token — get a new one from @BotFather |
| View CPD finds nobody | Data workbook missing/moved — re-check step 6 |
| Admin commands say "admin only" | Your ID is missing from `ADMIN_IDS` in `.env` |
