# ConstructivIQ Diagnostic Utility

A Python CLI tool for investigating Data Integration issues at ConstructivIQ.
Pulls errors and warnings from AWS CloudWatch Logs Insights and generates a
structured HTML report with a service-by-service breakdown.

---

## Quick start

```bash
cd ciq-diagnostic-utility
pip install -r requirements.txt
copy .env.example .env   # fill in AWS credentials
python diagnose.py --demo
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
copy .env.example .env
```

Edit `.env` and fill in:

| Variable | Description |
|---|---|
| `AWS_ACCESS_KEY_ID_PROD` | AWS access key for prod / us-east-1 |
| `AWS_SECRET_ACCESS_KEY_PROD` | AWS secret key for prod / us-east-1 |
| `AWS_ACCESS_KEY_ID_NONPROD` | AWS access key for dev / qa / perf (us-east-2) |
| `AWS_SECRET_ACCESS_KEY_NONPROD` | AWS secret key for dev / qa / perf (us-east-2) |
| `JIRA_BASE_URL` | Your Atlassian domain, e.g. `https://constructiviq.atlassian.net` |
| `JIRA_EMAIL` | Your Atlassian account email |
| `JIRA_API_TOKEN` | Create at https://id.atlassian.com/manage-profile/security/api-tokens |
| `ANTHROPIC_API_KEY` | Enables AI root-cause analysis (optional) |

> **Never commit `.env` to git.** It is listed in `.gitignore`.

---

## Usage

### Look up errors for a specific project

```bash
# Default: queries ECS + Lambda log groups for the project
python diagnose.py --project-id <uuid> --html

# Recommended: query key services only (auth, integration, date-block-engine,
#              report-engine, extraction) — faster and covers the most common failure points
python diagnose.py --project-id <uuid> --key-services --html

# Narrow the time window
python diagnose.py --project-id <uuid> --key-services --hours 72 --html

# Add a keyword filter
python diagnose.py --project-id <uuid> --key-services --filter "timeout" --html

# Query every log group in the region (slow — 100+ groups)
python diagnose.py --project-id <uuid> --all-log-groups --html
```

The HTML report's **Project Errors** tab shows:
- KPI tiles: total events, services with hits, latest timestamp, environment
- **Service Overview** table: one row per log group with error count
- **Per-service collapsible cards**: click to expand full error details (timestamp, level, import log ID, error type, message)
- Import Log IDs: all affected import_log_ids as copyable pills

### Key services scanned with `--key-services`

| Pattern matched | Examples |
|---|---|
| `auth` | authentication, authorisation services |
| `data` + `integr` | data-integration, dataintegration |
| `date` + `block` | date-block-engine |
| `report` + `engine` | report-engine |
| `extract` | extraction services |

Non-prod markers (`demo`, `sandbox`, `pilot`, `ciq-sb-`, `ciq-qa-`, etc.) are
automatically excluded when `--env prod` (the default).

### Investigate by environment

```bash
# Prod (default)
python diagnose.py --env prod --html

# Non-prod
python diagnose.py --env qa --html
python diagnose.py --env dev --hours 48 --html
```

### Investigate a Jira issue

```bash
python diagnose.py --issue CIQ-1234
```

### JQL query

```bash
python diagnose.py --jql "project=CIQ AND labels=prod-incident AND created >= -7d"
```

### List CloudWatch log groups

```bash
# List all groups in the environment
python diagnose.py --list-log-groups --env prod

# Filter by keyword
python diagnose.py --list-log-groups --log-group-filter auth --env prod
python diagnose.py --list-log-groups --log-group-filter date-block --env prod
```

### Demo mode (no credentials needed)

```bash
python diagnose.py --demo
```

---

## All CLI options

```
  --project-id UUID     Query errors for a specific project UUID
  --key-services        Query key services only: auth, integration,
                        date-block-engine, report-engine, extraction
  --all-log-groups      Query every log group in the region (may be slow)
  --env ENV             Environment: prod (default), qa, dev, perf, demo
  --hours INT           Look-back window in hours (default: 480 when --project-id set, else 24)
  --filter TEXT         Extra keyword filter applied to CWI query
  --html / --no-html    Generate HTML report (default: off)
  --open / --no-open    Auto-open report in browser after generation

  -i, --issue KEY       Jira issue key (e.g. CIQ-1234)
  --jql JQL             JQL query for related Jira issues
  --all-envs            Scan all environments
  --infra               Include infrastructure checks
  --waste               Include waste analysis
  --list-log-groups     List CloudWatch log groups for the environment
  --log-group-filter TEXT  Keyword filter for --list-log-groups
  --demo                Run with synthetic demo data
  -h, --help            Show help
```

---

## Environments and log groups

| Env | Region | ECS log group | Lambda log group |
|---|---|---|---|
| `dev` | us-east-2 | `/ecs/dev-ciq-dataintegration` | `/aws/lambda/ciq-dev-ciq-dataintegration` |
| `qa` | us-east-2 | `/ecs/qa-ciq-dataintegration` | `/aws/lambda/ciq-qa-ciq-dataintegration` |
| `perf` | us-east-2 | `/ecs/perf-ciq-dataintegration` | `/aws/lambda/ciq-perf-ciq-dataintegration` |
| `demo` | us-east-1 | `/ecs/ciq-demo2-useast1-data-integration-job` | `/aws/lambda/ciq-demo2-useast1-lambda-data-integration` |
| `prod` | us-east-1 | `/ecs/ciq-prod-useast1-data-integration-job` | `/aws/lambda/ciq-prod-useast1-lambda-data-integration` |

> The prod ECS group is ~64 GB — CloudWatch Insights queries can take 90–120 s.
> The tool polls up to 180 s and surfaces a timeout error if the query doesn't
> complete in time (rather than silently returning 0 results).

---

## Project structure

```
ciq-diagnostic-utility/
├── diagnose.py                      <- CLI entry point (Click)
├── config.py                        <- Env-var loader (.env via python-dotenv)
├── requirements.txt
├── .env.example                     <- Copy to .env and fill in
├── collectors/
│   ├── project_collector.py         <- CloudWatch Insights queries by project UUID
│   │                                   (collect_project, collect_project_key_services,
│   │                                    collect_project_all_groups)
│   ├── jira_collector.py            <- Jira REST API v3
│   ├── log_collector.py             <- Local log file scanner
│   ├── api_collector.py             <- HTTP health probes
│   └── email_collector.py           <- IMAP email fetcher
├── analyzers/
│   └── ai_analyzer.py               <- Claude API + heuristic fallback
├── reporters/
│   ├── cw_report.py                 <- CloudWatch HTML report generator
│   ├── html_reporter.py             <- General HTML report generator
│   └── tabs/
│       └── project.py               <- Project errors tab: service-wise view
└── sample_data/
    └── demo_data.py                 <- Synthetic demo scenario
```

---

## Extending the tool

- **New data source:** Add `collectors/my_source.py`, call it from `diagnose.py`.
- **New report tab:** Add a renderer in `reporters/tabs/` and wire it in `reporters/cw_report.py`.
- **Different log groups:** Update `_LOG_GROUPS` in `collectors/project_collector.py`.
- **Add a key service:** Append a pattern list to `_KEY_SERVICE_PATTERNS` in `collectors/project_collector.py`.
