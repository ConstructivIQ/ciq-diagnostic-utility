"""
collectors/log_collector.py
Reads application log files and extracts error/warning lines.
Supports plain text logs with common patterns (Python, Java/Spring, Node.js).
"""
from __future__ import annotations
import glob
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

LEVEL_RE = re.compile(
    r"\b(CRITICAL|FATAL|ERROR|WARN(?:ING)?|EXCEPTION|TRACEBACK)\b",
    re.IGNORECASE,
)
TIMESTAMP_PATTERNS = [
    re.compile(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"),
    re.compile(r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"),
]
STACK_TRACE_PREFIXES = ("  at ", "\tat ", "    ", "\tTraceback", "Caused by:")


@dataclass
class LogEntry:
    timestamp: Optional[str]
    level: str
    message: str
    source_file: str
    line_number: int
    raw_lines: list[str] = field(default_factory=list)


def collect(
    paths: list[str],
    since: Optional[datetime] = None,
    keyword: Optional[str] = None,
    max_entries: int = 200,
) -> list[LogEntry]:
    """Scan log files matched by paths (glob patterns accepted)."""
    entries: list[LogEntry] = []
    kw_re = re.compile(keyword, re.IGNORECASE) if keyword else None

    for pattern in paths:
        for filepath in sorted(glob.glob(pattern, recursive=True)):
            fp = Path(filepath)
            if not fp.is_file():
                continue
            entries.extend(_scan_file(fp, since, kw_re, max_entries))
            if len(entries) >= max_entries:
                break

    entries.sort(
        key=lambda e: (e.level.upper() not in ("ERROR", "CRITICAL", "FATAL"), e.timestamp or ""),
        reverse=True,
    )
    return entries[:max_entries]


def _scan_file(fp: Path, since: Optional[datetime], kw_re, max_entries: int) -> list[LogEntry]:
    entries: list[LogEntry] = []
    try:
        lines = fp.read_text(errors="replace").splitlines()
    except OSError:
        return entries

    i = 0
    while i < len(lines):
        line = lines[i]
        level_match = LEVEL_RE.search(line)
        if not level_match:
            i += 1
            continue
        ts = _parse_timestamp(line)
        if since and ts and ts < since.replace(tzinfo=None):
            i += 1
            continue
        if kw_re and not kw_re.search(line):
            i += 1
            continue
        raw = [line]
        j = i + 1
        while j < len(lines) and (lines[j].startswith(STACK_TRACE_PREFIXES) or not lines[j].strip()):
            raw.append(lines[j])
            j += 1
        entries.append(LogEntry(
            timestamp=ts.isoformat() if ts else None,
            level=level_match.group(1).upper(),
            message="\n".join(raw),
            source_file=str(fp),
            line_number=i + 1,
            raw_lines=raw,
        ))
        i = j
    return entries


def _parse_timestamp(line: str) -> Optional[datetime]:
    for pat in TIMESTAMP_PATTERNS:
        m = pat.match(line.strip())
        if m:
            raw = m.group(1)
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f",
                        "%b %d %H:%M:%S"):
                try:
                    return datetime.strptime(raw[:len(fmt)], fmt)
                except ValueError:
                    continue
    return None
