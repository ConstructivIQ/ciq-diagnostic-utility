#!/usr/bin/env python3
"""
diagnose.py - ConstructivIQ Diagnostic Utility
-----------------------------------------------
Usage examples:

  # Run with synthetic demo data (no credentials needed)
  python diagnose.py --demo

  # Investigate a specific Jira issue
  python diagnose.py --issue CIQ-1234

  # Full investigation
  python diagnose.py --issue CIQ-1234 \
      --logs /var/log/constructiviq/*.log \
      --api-base https://api.constructiviq.com \
      --email --email-keyword "login error" \
      --since 2026-08-20 \
      --output report.html

  # Check top errors in prod for the last hour
  python diagnose.py --env prod --hours 1 --top 10

  # Filter to ERROR+ severity only
  python diagnose.py --env prod --hours 12 --severity ERROR

  # Generate full HTML dashboard for all environments
  python diagnose.py --all-envs --hours 4 --html

  # Single-env HTML report
  python diagnose.py --env prod --hours 2 --html

  # Full report with infrastructure inventory (free)
  python diagnose.py --env prod --hours 1 --html --infra

  # Full report with infra + cost breakdown (⚠️ $0.01 AWS charge)
  python diagnose.py --env prod --hours 1 --html --infra --infra-cost

  # Full report with unused-resource detection (free — CloudWatch standard metrics)
  python diagnose.py --env prod --hours 1 --html --infra --waste

  # Everything: infra + cost + waste finder
  python diagnose.py --env prod --hours 1 --html --infra --infra-cost --waste
"""

import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--issue", "-i", default=None, metavar="KEY",
              help="Jira issue key to investigate (e.g. CIQ-1234)")
@click.option("--jql", default=None, metavar="JQL",
              help="JQL query to pull a set of related Jira issues")
@click.option("--logs", "-l", default=None, multiple=True, metavar="GLOB",
              help="Log file path(s) or glob pattern(s) -- repeatable")
@click.option("--api-base", default=None, metavar="URL",
              help="API base URL to probe (overrides .env)")
@click.option("--email/--no-email", default=False,
              help="Include support emails in the investigation")
@click.option("--email-keyword", default=None, metavar="TEXT",
              help="Keyword to filter support emails by subject")
@click.option("--since", default=None, metavar="YYYY-MM-DD",
              help="Only include log entries / emails after this date")
@click.option("--context", "-c", default="", metavar="TEXT",
              help="Extra context to pass to the AI (freeform)")
@click.option("--output", "-o", default=None, metavar="FILE",
              help="Output HTML report path (default: auto-named)")
@click.option("--max-logs", default=200, show_default=True,
              help="Maximum log entries to include")
@click.option("--max-emails", default=20, show_default=True,
              help="Maximum support emails to fetch")
@click.option("--cw-group", default=None, metavar="LOG_GROUP",
              help="CloudWatch log group name to fetch logs from")
@click.option("--cw-env", default="dev",
              type=click.Choice(["dev", "qa", "perf", "demo", "prod"], case_sensitive=False),
              show_default=True, help="Environment (sets AWS region automatically)")
@click.option("--cw-stream", default=None, metavar="STREAM",
              help="Narrow to a specific CloudWatch log stream (optional)")
@click.option("--cw-region", default=None, metavar="REGION",
              help="Override AWS region (e.g. us-east-1); inferred from --cw-env by default")
@click.option("--env", "-e", default="prod",
              type=click.Choice(["dev", "qa", "perf", "prod"], case_sensitive=False),
              help="Environment shortcut: fetch errors across Auth, Integration, "
                   "Report Engine and Audit Listener for this environment")
@click.option("--all-envs", "all_envs", is_flag=True, default=False,
              help="Query ALL environments (dev, qa, perf, prod) — best combined with --html")
@click.option("--hours", default=None, type=int,
              help="Hours to look back (default: 480 = 20 days when --project-id is set, else 24)")
@click.option("--top", default=10, show_default=True,
              help="Number of top errors to display per environment")
@click.option("--severity", "-s",
              type=click.Choice(["ALL", "ERROR", "WARN", "CRITICAL", "FATAL", "EXCEPTION"],
                                case_sensitive=False),
              default="ERROR", show_default=True,
              help="Filter to a specific severity level (ALL = show everything)")
@click.option("--html", "gen_html", is_flag=True, default=False,
              help="Generate a self-contained HTML dashboard (Customer Issues + Environment tabs)")
@click.option("--infra", "gen_infra", is_flag=True, default=False,
              help="Collect AWS infrastructure inventory for prod (free — describe_*/list_* calls only)")
@click.option("--infra-cost", "infra_cost", is_flag=True, default=False,
              help="Include Cost Explorer data in Infra tab  ⚠️  costs $0.01 per run")
@click.option("--waste", "gen_waste", is_flag=True, default=False,
              help="Check CloudWatch metrics to identify unused/idle AWS resources (free — standard metrics only). "
                   "Requires --infra to collect the resource list first.")
@click.option("--project-id", "project_id", default=None, metavar="UUID",
              help="Project UUID to inspect — adds a dedicated Project Errors tab "
                   "showing all CloudWatch error lines for that project_id")
@click.option("--filter", "message_filter", default=None, metavar="KEYWORD",
              help="Narrow --project-id results to log lines containing this keyword "
                   "(added as 'and @message like /KEYWORD/' in the CWI query)")
@click.option("--list-log-groups", "list_log_groups", is_flag=True, default=False,
              help="List all CloudWatch log groups in the environment's region and exit")
@click.option("--log-group-filter", "log_group_filter", default=None, metavar="TEXT",
              help="Filter --list-log-groups output by this substring (case-insensitive)")
@click.option("--demo", is_flag=True, default=False,
              help="Run with synthetic demo data (no credentials needed)")
@click.option("--open/--no-open", "open_report", default=True,
              help="Open the HTML report in your browser when done")
def main(issue, jql, logs, api_base, email, email_keyword,
         since, context, output, max_logs, max_emails, demo, open_report,
         cw_group, cw_env, cw_stream, cw_region,
         env, all_envs, hours, top, severity, gen_html, gen_infra, infra_cost, gen_waste,
         project_id, message_filter, list_log_groups, log_group_filter):
    """ConstructivIQ Diagnostic Utility — investigate production issues."""

    # Smart hours default: 20 days for project queries, 24h otherwise
    if hours is None:
        hours = 480 if project_id else 24

    # ── List log groups and exit ─────────────────────────────────────────────
    if list_log_groups:
        _REGION_MAP = {
            "dev": "us-east-2", "qa": "us-east-2", "perf": "us-east-2",
            "demo": "us-east-1", "prod": "us-east-1",
        }
        region = _REGION_MAP.get(env, "us-east-1")
        import boto3
        import config as _cfg
        from rich.table import Table
        _is_prod = (env or "prod") in ("prod", "demo") or region == "us-east-1"
        client = boto3.client(
            "logs", region_name=region,
            aws_access_key_id=_cfg.AWS_ACCESS_KEY_ID_PROD if _is_prod else _cfg.AWS_ACCESS_KEY_ID_NONPROD,
            aws_secret_access_key=_cfg.AWS_SECRET_ACCESS_KEY_PROD if _is_prod else _cfg.AWS_SECRET_ACCESS_KEY_NONPROD,
        )
        console.print(f"\n[bold]CloudWatch log groups[/bold] · region: [cyan]{region}[/cyan] "
                      f"(--env [cyan]{env}[/cyan])"
                      + (f"  filter: [yellow]{log_group_filter}[/yellow]" if log_group_filter else ""))
        table = Table(show_header=True, header_style="bold", show_lines=False, box=None)
        table.add_column("#", style="dim", width=4)
        table.add_column("Log Group", style="cyan")
        table.add_column("Retained (days)", justify="right", style="dim")
        table.add_column("Size (MB)", justify="right", style="dim")
        paginator = client.get_paginator("describe_log_groups")
        groups = []
        for page in paginator.paginate():
            for g in page.get("logGroups", []):
                name = g["logGroupName"]
                if log_group_filter and log_group_filter.lower() not in name.lower():
                    continue
                groups.append(g)
        groups.sort(key=lambda g: g["logGroupName"])
        for i, g in enumerate(groups, 1):
            retention = str(g.get("retentionInDays", "∞"))
            size_mb = f'{g.get("storedBytes", 0) / 1_048_576:.1f}'
            table.add_row(str(i), g["logGroupName"], retention, size_mb)
        console.print(table)
        console.print(f"\n[dim]{len(groups)} group(s) found[/dim]\n")
        return

    console.print(Panel.fit(
        "[bold white]ConstructivIQ Diagnostic Utility[/bold white]\n"
        "[dim]AI-powered root-cause analysis for production issues[/dim]",
        border_style="blue",
    ))

    # ── CloudWatch environment error-check mode (--env / --all-envs) ───────────
    # Default to prod when no investigation-mode flags are given
    if not env and not all_envs and not issue and not jql and not list(logs) and not cw_group and not demo and not project_id:
        env = "prod"

    # ── Project-only mode ────────────────────────────────────────────────────
    # When --project-id is set, skip ALL env scanning (Auth, Integration,
    # Report Engine services). Always fetch project errors and print a
    # terminal summary; also generate HTML when --html is passed.
    if project_id:
        project_env = env or "prod"
        from collectors.project_collector import collect_project
        project_data = None
        console.print(
            f"\n[bold]Querying CloudWatch…[/bold] project=[cyan]{project_id}[/cyan]  "
            f"env=[cyan]{project_env.upper()}[/cyan]  window=[cyan]{hours}h[/cyan]"
            + (f"  filter=[cyan]{message_filter}[/cyan]" if message_filter else "")
            + "\n[dim](ECS + Lambda log groups, polling up to 60s each — please wait)[/dim]"
        )
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
            console=console, transient=False,
        ) as proj_progress:
            ptask = proj_progress.add_task(
                f"Starting CWI query for {project_id[:8]}…",
                total=None,
            )
            try:
                proj_progress.update(ptask, description="Querying ECS log group…")
                project_data = collect_project(
                    project_id, env=project_env, hours=hours,
                    message_filter=message_filter,
                )
                n = project_data.get("total", 0)
                unknown = project_data.get("unknown_groups", False)
                suffix = " ⚠️ prod log groups unknown" if unknown else ""
                proj_progress.update(
                    ptask,
                    description=f"[green]✓ Done — {n} event(s) found{suffix}"
                )
            except Exception as exc:
                proj_progress.update(
                    ptask,
                    description=f"[red]✗ Fetch failed — {exc}"
                )

        # Terminal summary table
        if project_data:
            from rich.table import Table
            errors = project_data.get("errors", [])
            total  = project_data.get("total", 0)
            console.print(
                f"\n[bold]Project:[/bold] [cyan]{project_id}[/cyan]  |  "
                f"[bold]Env:[/bold] {project_env.upper()}  |  "
                f"[bold]Window:[/bold] last {hours}h  |  "
                f"[bold]Events:[/bold] {total}"
                + (f"  |  [bold]Filter:[/bold] {message_filter}" if message_filter else "")
            )
            if errors:
                tbl = Table(show_header=True, header_style="bold", show_lines=False, box=None)
                tbl.add_column("Timestamp", style="dim", width=24)
                tbl.add_column("Src", width=6)
                tbl.add_column("Lvl", width=6)
                tbl.add_column("Import Log ID", width=36)
                tbl.add_column("Error", style="red")
                tbl.add_column("Message")
                for r in errors[:top]:
                    lvl_style = "red" if r.get("level", "ERROR") in ("ERROR", "CRITICAL", "FATAL") else "yellow"
                    tbl.add_row(
                        r.get("ts", ""),
                        r.get("source", ""),
                        f"[{lvl_style}]{r.get('level','ERROR')}[/{lvl_style}]",
                        r.get("import_log_id", "—"),
                        r.get("error_name", ""),
                        r.get("message", r.get("raw", ""))[:120],
                    )
                console.print(tbl)
                if total > top:
                    console.print(f"[dim]… {total - top} more events — use --html to see all[/dim]")
            else:
                console.print("[dim]No errors or warnings found.[/dim]")

        if gen_html and project_data:
            from reporters.cw_report import generate_cw_report
            out_path = Path(output) if output else Path("cw_report.html")
            path = generate_cw_report(
                {}, hours=hours, output_path=out_path,
                jira_tickets=[], sync_data=None, emails=[],
                rds_snap=None, infra_data=None, waste_data=None,
                project_id=project_id, project_data=project_data,
            )
            console.print(f"\n[bold green]✅ HTML report:[/bold green] {path.resolve()}")
            if open_report:
                import webbrowser
                webbrowser.open(path.resolve().as_uri())
        return

    if env or all_envs:
        from check_errors import collect_env, print_env_table, LOG_GROUPS
        from reporters.cw_report import generate_cw_report

        envs_to_query = list(LOG_GROUPS.keys()) if all_envs else [env]

        console.print(
            f"\n[bold]Environments:[/bold] {', '.join(e.upper() for e in envs_to_query)}  |  "
            f"[bold]Window:[/bold] last {hours}h  |  "
            f"[bold]Severity:[/bold] {severity}  |  "
            f"[bold]Top:[/bold] {top} errors\n"
        )

        env_results = {}

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console, transient=True) as progress:
            for current_env in envs_to_query:
                task = progress.add_task(
                    f"Fetching {current_env.upper()}…", total=None)
                try:
                    env_results[current_env] = collect_env(current_env, hours, severity)
                    n = env_results[current_env].get("total_events", 0)
                    progress.update(
                        task,
                        description=f"[green]{current_env.upper()}: {n} events fetched"
                    )
                except Exception as exc:
                    progress.update(
                        task,
                        description=f"[red]{current_env.upper()}: failed — {exc}"
                    )

        # Print terminal tables (skip if --html and querying multiple envs)
        for current_env, d in env_results.items():
            if not gen_html or len(envs_to_query) == 1:
                print_env_table(current_env, d, top, hours)

        # Generate HTML dashboard
        if gen_html:
            # ── When --project-id is set, skip all other tabs entirely ────────
            # Only the Project Errors tab is rendered; all other fetches are
            # skipped so the command is fast and focused.
            if project_id:
                jira_tickets = []
                sync_data    = None
                emails       = []
                rds_snap     = None
                infra_data   = None
                waste_data   = None
            else:
                # Fetch Jira Prod_Issue tickets for the Customer Tickets tab.
                # NOTE: This is intentionally env-independent — the Customer Tickets tab
                # always shows the same Jira data (Prod_Issue label) regardless of which
                # CloudWatch environment (--env dev/qa/perf/prod / --all-envs) is selected.
                # fetch_prod_issues() uses a fixed JQL with no env parameter.
                jira_tickets = []
                with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                              console=console, transient=True) as jira_progress:
                    jtask = jira_progress.add_task("Fetching Jira Prod_Issue tickets…", total=None)
                    try:
                        from collectors.jira_collector import fetch_prod_issues
                        jira_tickets = fetch_prod_issues()
                        jira_progress.update(
                            jtask,
                            description=f"[green]Jira: {len(jira_tickets)} Prod_Issue tickets"
                        )
                    except Exception as exc:
                        jira_progress.update(
                            jtask,
                            description=f"[yellow]Jira fetch skipped — {exc}"
                        )

                # ── Integration Sync Failures tab: always Prod, always 24h ─────────
                sync_data = None
                if "prod" in env_results and hours == 24:
                    sync_data = env_results["prod"]
                else:
                    with Progress(
                        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                        console=console, transient=True,
                    ) as sync_progress:
                        stask = sync_progress.add_task(
                            "Fetching Prod 24h data for Integration Sync Failures…", total=None)
                        try:
                            from check_errors import collect_env as _collect_env
                            sync_data = _collect_env("prod", 24, "ALL")
                            n = sync_data.get("total_events", 0)
                            sync_progress.update(
                                stask,
                                description=f"[green]Prod 24h: {n} events fetched"
                            )
                        except Exception as exc:
                            sync_progress.update(
                                stask,
                                description=f"[yellow]Prod 24h fetch skipped — {exc}"
                            )

                # ── Support Emails tab: always last 2 days from shared inbox ─────────
                emails = []
                with Progress(
                    SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                    console=console, transient=True,
                ) as email_progress:
                    etask = email_progress.add_task(
                        "Fetching support emails (last 2 days)…", total=None)
                    try:
                        from collectors.email_collector import fetch_emails
                        emails = fetch_emails(since_days=2, max_messages=200)
                        email_progress.update(
                            etask,
                            description=f"[green]Emails: {len(emails)} fetched"
                        )
                    except Exception as exc:
                        email_progress.update(
                            etask,
                            description=f"[yellow]Email fetch skipped — {exc}"
                        )

                # ── RDS tab: PostgreSQL health snapshot ───────────────────────────
                rds_snap = None
                with Progress(
                    SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                    console=console, transient=True,
                ) as rds_progress:
                    rtask = rds_progress.add_task(
                        "Fetching RDS health snapshot…", total=None)
                    try:
                        from collectors.rds_collector import fetch_snapshot
                        rds_snap = fetch_snapshot()
                        if rds_snap.connected:
                            rds_progress.update(
                                rtask,
                                description=f"[green]RDS: connected ({rds_snap.total_connections}/{rds_snap.max_connections} conns)"
                            )
                        else:
                            rds_progress.update(
                                rtask,
                                description=f"[yellow]RDS: {rds_snap.error}"
                            )
                    except Exception as exc:
                        rds_progress.update(
                            rtask,
                            description=f"[yellow]RDS fetch skipped — {exc}"
                        )

            # ── Infra tab: AWS resource inventory (always prod) ───────────────
            infra_data = None
            if gen_infra and not project_id:
                from collectors.infra_collector import collect_infra
                import config as _cfg
                _account, _region = "prod", "us-east-1"
                with Progress(
                    SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                    console=console, transient=True,
                ) as infra_progress:
                    itask = infra_progress.add_task(
                        f"Collecting AWS infra (prod / {_region})"
                        + (" + cost ⚠️ $0.01" if infra_cost else " — free") + "…",
                        total=None,
                    )
                    try:
                        infra_data = collect_infra(
                            env="prod", account=_account, region=_region,
                            include_cost=infra_cost,
                        )
                        total_res = sum(
                            len([r for r in lst if not r.get("_error")])
                            for lst in infra_data.get("services", {}).values()
                        )
                        infra_progress.update(
                            itask,
                            description=f"[green]Infra: {total_res} resources collected"
                        )
                    except Exception as exc:
                        infra_progress.update(
                            itask,
                            description=f"[yellow]Infra collection skipped — {exc}"
                        )

            # ── Waste Finder: CloudWatch utilisation check (free) ─────────────
            waste_data = None
            if gen_waste and not project_id:
                if infra_data is None:
                    console.print(
                        "[yellow]⚠️  --waste requires --infra (need resource list to check). "
                        "Add --infra to your command.[/yellow]"
                    )
                else:
                    from collectors.waste_collector import collect_waste
                    with Progress(
                        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                        console=console, transient=True,
                    ) as waste_progress:
                        wtask = waste_progress.add_task(
                            "Checking CloudWatch for unused/idle resources (14-day look-back)…",
                            total=None,
                        )
                        try:
                            waste_data = collect_waste(infra_data, days=14)
                            n = waste_data.get("total", 0)
                            waste_progress.update(
                                wtask,
                                description=f"[green]Waste: {n} unused/idle resource(s) found"
                            )
                        except Exception as exc:
                            waste_progress.update(
                                wtask,
                                description=f"[yellow]Waste check skipped — {exc}"
                            )

            # ── Project Errors tab: per-project CloudWatch drill-down ────────
            project_data = None
            if project_id:
                with Progress(
                    SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                    console=console, transient=True,
                ) as proj_progress:
                    ptask = proj_progress.add_task(
                        f"Fetching errors for project {project_id[:8]}… ({env}, last {hours}h)…",
                        total=None,
                    )
                    try:
                        from collectors.project_collector import collect_project
                        project_data = collect_project(project_id, env=env, hours=hours,
                                                       message_filter=message_filter)
                        n = project_data.get("total", 0)
                        unknown = project_data.get("unknown_groups", False)
                        suffix = " ⚠️ prod log groups unknown" if unknown else ""
                        proj_progress.update(
                            ptask,
                            description=f"[green]Project: {n} error(s) found{suffix}"
                        )
                    except Exception as exc:
                        proj_progress.update(
                            ptask,
                            description=f"[yellow]Project fetch skipped — {exc}"
                        )

            out_path = Path(output) if output else Path("cw_report.html")
            path = generate_cw_report(
                env_results, hours=hours, output_path=out_path,
                jira_tickets=jira_tickets,
                sync_data=sync_data,
                emails=emails,
                rds_snap=rds_snap,
                infra_data=infra_data,
                waste_data=waste_data,
                project_id=project_id,
                project_data=project_data,
            )
            console.print(f"\n[bold green]✅ HTML report:[/bold green] {path.resolve()}")
            if open_report:
                import webbrowser
                webbrowser.open(path.resolve().as_uri())

        return

    # ── Full investigation mode ────────────────────────────────────────────────
    since_dt = None
    if since:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            console.print(f"[red]Invalid --since date '{since}'. Expected YYYY-MM-DD.[/red]")
            sys.exit(1)

    jira_issue = None
    jira_related = []
    log_entries = []
    api_results = []
    email_messages = []

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console, transient=True) as progress:

        if demo:
            task = progress.add_task("Loading demo data...", total=None)
            from sample_data import demo_data
            jira_issue = demo_data.JIRA_ISSUE
            log_entries = demo_data.LOG_ENTRIES
            api_results = demo_data.API_RESULTS
            email_messages = demo_data.EMAIL_MESSAGES
            progress.update(task, description="[green]Demo data loaded")
        else:
            if issue:
                task = progress.add_task(f"Fetching Jira issue {issue}...", total=None)
                try:
                    from collectors import jira_collector
                    jira_issue = jira_collector.fetch_issue(issue)
                    progress.update(task, description=f"[green]Jira {issue} fetched")
                except Exception as exc:
                    progress.update(task, description=f"[yellow]Jira fetch failed: {exc}")
                    console.print(f"[yellow]Warning: Could not fetch Jira issue: {exc}[/yellow]")

            if jql:
                task = progress.add_task("Running JQL query...", total=None)
                try:
                    from collectors import jira_collector
                    jira_related = jira_collector.search_issues(jql)
                    progress.update(task, description=f"[green]JQL returned {len(jira_related)} issues")
                except Exception as exc:
                    progress.update(task, description=f"[yellow]JQL failed: {exc}")

            log_paths = list(logs) or []
            if not log_paths:
                import config
                log_paths = config.LOG_PATHS

            if log_paths:
                task = progress.add_task("Scanning log files...", total=None)
                try:
                    from collectors import log_collector
                    log_entries = log_collector.collect(
                        paths=log_paths, since=since_dt,
                        keyword=issue or email_keyword, max_entries=max_logs,
                    )
                    progress.update(task, description=f"[green]Found {len(log_entries)} log entries")
                except Exception as exc:
                    progress.update(task, description=f"[yellow]Log scan failed: {exc}")

            if cw_group:
                task = progress.add_task(
                    f"Fetching CloudWatch logs [{cw_env.upper()}]...", total=None)
                try:
                    from collectors import cloudwatch_collector
                    cw_entries = cloudwatch_collector.collect(
                        log_group=cw_group, env=cw_env, region=cw_region,
                        log_stream=cw_stream, since=since_dt, max_entries=max_logs,
                    )
                    log_entries.extend(cw_entries)
                    progress.update(
                        task,
                        description=f"[green]CloudWatch: {len(cw_entries)} entries from {cw_group}",
                    )
                except Exception as exc:
                    progress.update(task, description=f"[yellow]CloudWatch failed: {exc}")
                    console.print(f"[yellow]Warning: CloudWatch error: {exc}[/yellow]")

            task = progress.add_task("Probing API endpoints...", total=None)
            try:
                from collectors import api_collector
                api_results = api_collector.probe_standard_endpoints(api_base)
                progress.update(task, description=f"[green]API probes done ({len(api_results)} checks)")
            except Exception as exc:
                progress.update(task, description=f"[yellow]API probe failed: {exc}")

            if email:
                task = progress.add_task("Fetching support emails...", total=None)
                try:
                    from collectors import email_collector
                    days = (datetime.now() - since_dt).days if since_dt else 7
                    email_messages = email_collector.fetch_emails(
                        keyword=email_keyword or issue, since_days=days, max_messages=max_emails,
                    )
                    progress.update(task, description=f"[green]{len(email_messages)} emails fetched")
                except Exception as exc:
                    progress.update(task, description=f"[yellow]Email fetch failed: {exc}")

        # Evidence summary
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column(style="dim", width=22)
        t.add_column()
        t.add_row("Jira issue", jira_issue.get("key") if jira_issue else "---")
        t.add_row("Log entries", str(len(log_entries)))
        t.add_row("API probes", str(len(api_results)))
        t.add_row("Emails", str(len(email_messages)))
        console.print(t)

        # Analyse
        task = progress.add_task("Analysing with Claude AI...", total=None)
        from analyzers import ai_analyzer
        analysis = ai_analyzer.analyze(
            issue=jira_issue, log_entries=log_entries,
            api_results=api_results, email_messages=email_messages,
            extra_context=context,
        )
        progress.update(task, description="[green]AI analysis complete")

    _print_summary(analysis)

    out_path = Path(output) if output else Path(
        f"diagnostic_{(jira_issue or {}).get('key', 'report')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    )
    from reporters import html_reporter
    report_path = html_reporter.generate_report(
        analysis=analysis, issue=jira_issue,
        log_entries=log_entries, api_results=api_results,
        email_messages=email_messages, output_path=out_path,
    )
    console.print(f"\n[bold green]Report written to:[/bold green] {report_path.resolve()}")

    if open_report:
        import webbrowser
        webbrowser.open(report_path.resolve().as_uri())


def _print_summary(analysis) -> None:
    color = {"CRITICAL": "red", "HIGH": "orange1",
             "MEDIUM": "yellow", "LOW": "green"}.get(analysis.severity.upper(), "yellow")
    console.print(f"\n[bold]Severity:[/bold] [{color}]{analysis.severity}[/{color}]"
                  f"  |  Confidence: {analysis.confidence}")
    console.print(f"\n[bold]Summary:[/bold] {analysis.summary}")
    console.print(f"\n[bold]Root Cause:[/bold] {analysis.likely_root_cause}")
    if analysis.recommended_actions:
        console.print("\n[bold]Recommended Actions:[/bold]")
        for i, action in enumerate(analysis.recommended_actions, 1):
            console.print(f"  {i}. {action}")


if __name__ == "__main__":
    main()
