# ConstructivIQ Diagnostic Utility

A Python CLI tool that investigates production issues by pulling evidence from
Jira, application logs, API health endpoints, and support email — then uses
the Claude AI to synthesise a root-cause analysis and generate a structured
HTML report.

---

## Quick start (demo — no credentials needed)

```bash
cd ciq-diagnostic-utility
pip install -r requirements.txt
python diagnose.py --demo
```

This runs a synthetic scenario (CIQ-4891: dashboard failing after 18:00 UTC)
and opens the HTML report in your browser.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
copy .env.example .env
# Edit .env and fill in your values
```

| Variable | Description |
|---|---|
| `JIRA_BASE_URL` | Your Atlassian domain, e.g. `https://constructiviq.atlassian.net` |
| `JIRA_EMAIL` | Your Atlassian account email |
| `JIRA_API_TOKEN` | Create at https://id.atlassian.com/manage-profile/security/api-tokens |
| `ANTHROPIC_API_KEY` | Enables AI root-cause analysis — tool degrades to heuristic without it |
| `EMAIL_HOST` / `EMAIL_USER` / `EMAIL_PASSWORD` | IMAP credentials for support inbox |
| `LOG_PATHS` | Comma-separated log file paths or glob patterns |
| `API_BASE_URL` | Base URL of the ConstructivIQ API to health-check |

---

## Usage

### Investigate a single Jira issue

```bash
python diagnose.py --issue CIQ-1234
```

### Include local log files

```bash
python diagnose.py --issue CIQ-1234 --logs "C:\logs\constructiviq\*.log"
```

### Full investigation

```bash
python diagnose.py ^
  --issue CIQ-1234 ^
  --logs "C:\logs\constructiviq\*.log" ^
  --api-base https://api.constructiviq.com ^
  --email --email-keyword "login error" ^
  --since 2026-08-20 ^
  --output report.html
```

### JQL query (pull a set of related issues)

```bash
python diagnose.py --jql "project=CIQ AND labels=prod-incident AND created >= -7d"
```

### All CLI options

```
  -i, --issue KEY       Jira issue key (e.g. CIQ-1234)
  --jql JQL             JQL query for related Jira issues
  -l, --logs GLOB       Log file path or glob -- repeatable
  --api-base URL        API base URL to probe
  --email / --no-email  Include support emails
  --email-keyword TEXT  Subject filter for emails
  --since YYYY-MM-DD    Only include data after this date
  -c, --context TEXT    Extra freeform context for the AI
  -o, --output FILE     Output HTML report path
  --max-logs INT        Max log entries (default: 200)
  --max-emails INT      Max emails (default: 20)
  --demo                Run with synthetic demo data
  --open / --no-open    Auto-open report in browser
  -h, --help            Show help
```

---

## Project structure

```
ciq-diagnostic-utility/
├── diagnose.py                  <- CLI entry point (Click)
├── config.py                    <- Env-var config loader
├── requirements.txt
├── .env.example                 <- Copy to .env and fill in
├── collectors/
│   ├── jira_collector.py        <- Jira REST API v3
│   ├── log_collector.py         <- Local log file scanner
│   ├── api_collector.py         <- HTTP health probes
│   └── email_collector.py       <- IMAP email fetcher
├── analyzers/
│   └── ai_analyzer.py           <- Claude API + heuristic fallback
├── reporters/
│   └── html_reporter.py         <- Self-contained HTML report generator
└── sample_data/
    └── demo_data.py             <- Synthetic CIQ-4891 scenario
```

---

## Extending the tool

- **New data source:** Add `collectors/my_source.py`, call it from `diagnose.py`,
  pass results to `ai_analyzer.analyze()` via `extra_context`.
- **Customise AI prompt:** Edit `_system_prompt()` in `analyzers/ai_analyzer.py`.
- **New report sections:** Add `_render_*()` in `reporters/html_reporter.py`.
