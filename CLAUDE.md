# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-purpose script that checks prices for tracked items on rodentpro.com and sends an
email/SMS notification when a price drops to or below a target. It runs both on demand and
automatically once a day via a macOS `launchd` agent.

## Commands

Run a price check manually:
```
python3 price_tracker.py
```

View the run history:
```
cat logs/price_tracker.log
```

Manage the daily launchd schedule (currently set to run at 8:00 PM):
```
launchctl load ~/Library/LaunchAgents/com.nataliavolkova.rodentpro.pricecheck.plist    # activate
launchctl unload ~/Library/LaunchAgents/com.nataliavolkova.rodentpro.pricecheck.plist  # deactivate
launchctl list | grep rodentpro                                                        # check status
```
launchd's own stdout/stderr for the scheduled run land in `logs/launchd.out.log` and
`logs/launchd.err.log` (should normally be empty — actual run output goes to
`logs/price_tracker.log` via the script's own logging).

No test suite, linter, or build step — this is a single script with no dependencies outside
the Python standard library.

## Architecture

- **`price_tracker.py`** — the entire application. Reads `items.json`, fetches each product
  page over HTTP, extracts price data, compares to the target, and notifies on a hit.
- **`items.json`** — the list of tracked items (`name`, `url`, `target_price`). Add/remove
  entries here to change what's tracked; no code changes needed.
- **`secrets.json`** (gitignored, not committed) — Gmail sender credentials (`gmail_address`,
  `gmail_app_password`, `notify_email`, optional `sms_gateway`) used to send the alert email/SMS.
  `gmail_app_password` is a Google-generated App Password, not the account's real password.
  `secrets.example.json` is the committed template. If neither `secrets.json` nor the
  `GMAIL_ADDRESS`/`GMAIL_APP_PASSWORD` environment variables are present, `load_secrets()` returns
  `None` and the script logs a warning and skips email/SMS but still completes the price check.
- **`com.nataliavolkova.rodentpro.pricecheck.plist`** — the launchd job definition (source of
  truth for the copy installed at `~/Library/LaunchAgents/`). Edit this file and re-run
  `launchctl unload` + `launchctl load` to change the schedule.

### Price extraction

rodentpro.com product pages embed a schema.org `Product` block as `<script
type="application/ld+json">` JSON, including `offers.price`. `price_tracker.py` parses that
block directly (regex to isolate the script tag, `html.unescape`, then `json.loads`) rather than
scraping visible HTML/CSS — the JSON-LD is far more stable across site redesigns than markup or
class names. If rodentpro.com ever drops this structured data, `fetch_price()` is the only
function that needs to change.

### Notification paths

- **Email** (working): sent via Gmail SMTP (`smtplib.SMTP_SSL`) using the credentials in
  `secrets.json`, to `notify_email`.
- **SMS** (working): reuses the same Gmail SMTP send, addressed to `secrets["sms_gateway"]`
  instead of `notify_email` — a carrier email-to-SMS gateway address (e.g.
  `<number>@tmomail.net` for T-Mobile). Sends a short version of the alert body with the same
  subject as the email. Skipped if `sms_gateway` isn't set in `secrets.json`.
There was an earlier attempt at a macOS desktop notification via `osascript -e 'display
notification ...'`, later dropped: Terminal.app never registers with Notification Center on this
machine, so the call silently did nothing, and a compiled-`.app` workaround via `osacompile` was
also abandoned (command-line argv didn't reach `on run argv` reliably when launched that way).

### Failure handling

A per-item fetch/parse failure is logged (`logger.error`) but does not stop the other items from
being checked, and does not block the email/SMS for any items that did succeed.
