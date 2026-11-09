"""
analyzers/ai_analyzer.py
Uses the Claude API to synthesize findings from all data sources
into a structured diagnostic analysis.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Optional
import config


@dataclass
class DiagnosticAnalysis:
    severity: str
    summary: str
    likely_root_cause: str
    contributing_factors: list[str]
    affected_components: list[str]
    recommended_actions: list[str]
    open_questions: list[str]
    confidence: str
    raw_ai_response: str = ""


def analyze(
    issue: Optional[dict] = None,
    log_entries: Optional[list] = None,
    api_results: Optional[list] = None,
    email_messages: Optional[list] = None,
    extra_context: str = "",
) -> DiagnosticAnalysis:
    """Send all collected evidence to Claude and get back a structured diagnosis."""
    if not config.ANTHROPIC_API_KEY:
        return _heuristic_analysis(issue, log_entries, api_results, email_messages)

    prompt = _build_prompt(issue, log_entries, api_results, email_messages, extra_context)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        message = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=2048,
            system=_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        return _parse_ai_response(raw)
    except Exception as exc:
        fallback = _heuristic_analysis(issue, log_entries, api_results, email_messages)
        fallback.summary = f"AI analysis unavailable ({exc}). Heuristic summary follows.\n" + fallback.summary
        return fallback


def _system_prompt() -> str:
    return """You are a senior site-reliability engineer and expert debugger for ConstructivIQ.
You receive evidence gathered from Jira tickets, application logs, API health checks, and support emails.
Your job is to produce a concise, structured root-cause analysis.

Respond ONLY with a JSON object matching this schema (no markdown fences, pure JSON):
{
  "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
  "summary": "<2-3 sentence executive summary>",
  "likely_root_cause": "<most probable root cause, specific>",
  "contributing_factors": ["<factor 1>", "<factor 2>"],
  "affected_components": ["<component/service 1>"],
  "recommended_actions": ["<action 1 - owner>", "<action 2 - owner>"],
  "open_questions": ["<question 1>"],
  "confidence": "<HIGH|MEDIUM|LOW>"
}"""


def _build_prompt(issue, log_entries, api_results, email_messages, extra_context) -> str:
    sections: list[str] = []
    if issue:
        sections.append(f"## Jira Issue: {issue.get('key')}\n"
                        f"**Summary:** {issue.get('summary')}\n"
                        f"**Status:** {issue.get('status')} | **Priority:** {issue.get('priority')}\n"
                        f"**Description:**\n{issue.get('description', '(none)')}\n")
        for c in (issue.get("comments") or [])[-5:]:
            sections.append(f"  [{c['created']}] {c['author']}: {c['body'][:400]}")
    if log_entries:
        sections.append(f"\n## Application Logs ({len(log_entries)} entries)")
        for entry in log_entries[:20]:
            sections.append(f"[{entry.timestamp or '?'}] [{entry.level}] {entry.source_file}:{entry.line_number}\n{entry.message[:600]}")
    if api_results:
        sections.append(f"\n## API Health Probes")
        for r in api_results:
            status = "OK" if r.ok else "FAIL"
            sections.append(f"{status} {r.url} -> HTTP {r.status_code} ({r.latency_ms}ms)"
                            + (f" ERROR: {r.error}" if r.error else ""))
    if email_messages:
        sections.append(f"\n## Support Emails ({len(email_messages)} messages)")
        for em in email_messages[:5]:
            sections.append(f"From: {em.sender} | {em.date}\nSubject: {em.subject}\n{em.body[:400]}")
    if extra_context:
        sections.append(f"\n## Additional Context\n{extra_context}")
    return "\n".join(sections)


def _parse_ai_response(raw: str) -> DiagnosticAnalysis:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        return DiagnosticAnalysis(
            severity=data.get("severity", "MEDIUM"),
            summary=data.get("summary", ""),
            likely_root_cause=data.get("likely_root_cause", ""),
            contributing_factors=data.get("contributing_factors", []),
            affected_components=data.get("affected_components", []),
            recommended_actions=data.get("recommended_actions", []),
            open_questions=data.get("open_questions", []),
            confidence=data.get("confidence", "MEDIUM"),
            raw_ai_response=raw,
        )
    except json.JSONDecodeError:
        return DiagnosticAnalysis(
            severity="MEDIUM", summary=raw[:500],
            likely_root_cause="See AI response above.",
            contributing_factors=[], affected_components=[],
            recommended_actions=[], open_questions=[],
            confidence="LOW", raw_ai_response=raw,
        )


def _heuristic_analysis(issue, log_entries, api_results, email_messages) -> DiagnosticAnalysis:
    factors: list[str] = []
    components: list[str] = []
    actions: list[str] = []
    error_count = len([e for e in (log_entries or []) if (e.level or "").upper() in ("ERROR", "CRITICAL")])
    api_failures = [r for r in (api_results or []) if not r.ok]
    if error_count:
        factors.append(f"{error_count} ERROR/CRITICAL log entries found")
    if api_failures:
        factors.append(f"{len(api_failures)} API endpoint(s) failing: " +
                       ", ".join(r.url for r in api_failures[:3]))
        actions.append("Investigate failing API endpoints immediately")
    if issue:
        components.extend(issue.get("components", []))
        factors.append(f"Jira issue {issue.get('key')}: {issue.get('summary')}")
    severity = "HIGH" if (api_failures or error_count > 10) else "MEDIUM"
    return DiagnosticAnalysis(
        severity=severity,
        summary=f"Heuristic analysis (AI not configured). Found {error_count} log errors and {len(api_failures)} API failures.",
        likely_root_cause="Requires manual investigation — ANTHROPIC_API_KEY not set in .env.",
        contributing_factors=factors,
        affected_components=list(set(components)) or ["Unknown"],
        recommended_actions=actions or ["Review logs and API health manually"],
        open_questions=["What changed in the last deployment?", "Are there database or cache issues?"],
        confidence="LOW",
    )
