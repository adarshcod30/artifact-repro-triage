"""Export the coding agent's session transcript as a readable, redacted trajectory.

Claude Code (Opus) wrote this repository. The challenge requires a trajectory for
every agent used, so the build agent gets one too - the tool calls it made, how
the tools responded, and the human checkpoints along the way.

REDACTION IS NOT OPTIONAL. A raw transcript contains whatever scrolled past:
environment variables, key material echoed by a shell, file contents. Ground rule
8 requires credentials stay outside the submission, so every line is filtered
before it is written, and the exporter refuses to write at all if a known secret
pattern survives the filter.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TRANSCRIPT_DIR = Path.home() / ".claude/projects"
OUT = Path("trajectories/build-agent.md")
MAX_CHARS = 1200  # per tool result, so the document stays readable

def _foreign_pattern() -> str:
    """Match identifiers belonging to a DIFFERENT project's transcripts.

    Built from what is on disk, not a hardcoded name: each sibling directory
    under ~/.claude/projects, the session ids inside it, and the repository name
    at the end of the directory slug.

    A first attempt took every trailing segment, which included `adarsh` - the
    home-directory segment shared by every absolute path in the transcript. It
    fired 1,059 times and rewrote `cd "/Users/adarsh/..."` into
    `cd "[REDACTED] ..."`, destroying the document to hide nothing.
    
    So any token that also appears in THIS project's own path is excluded: a
    redactor that mangles the thing it is protecting has failed twice.
    """
    mine = "".join(c if c.isalnum() else "-" for c in str(Path.cwd()))
    lower_mine = mine.lower()
    toks: set[str] = set()
    root = Path.home() / ".claude/projects"
    if root.is_dir():
        for d in root.iterdir():
            if not d.is_dir() or d.name == mine:
                continue
            toks.add(d.name)                       # the full slug: unambiguous
            for f in d.glob("*.jsonl"):
                toks.add(f.stem)                   # session ids: unambiguous
            tail = d.name.rstrip("-").split("-")[-1]
            if len(tail) >= 6 and tail.lower() not in lower_mine:
                toks.add(tail)
    if not toks:
        return r"(?!x)x"                           # matches nothing
    body = "|".join(re.escape(t) for t in sorted(toks, key=len, reverse=True))
    return rf"[^\s\"']*(?:{body})[^\s\"'\\]*"


# Ordered most-specific first. Each pattern is a distinct way a secret leaks.
REDACTIONS: list[tuple[str, re.Pattern]] = [
    # Identifiers of OTHER projects on this machine. Not credentials, but this
    # document is published, and the name of an unrelated repository - or the
    # id of a session belonging to one - is not the submission's to disclose.
    #
    # Found when the exporter itself picked another project's transcript and a
    # diagnostic printed the path here. Paths were redacted first; the NAMES
    # still appeared in prose, because a redactor that only handles the shape it
    # first noticed misses the same secret written a different way.
    # Case-insensitive: the name also appeared lower-cased inside shell
    # commands. Safe here because tokens shared with this project's own path
    # are already excluded, so widening cannot re-mangle our own paths.
    ("foreign_project", re.compile(_foreign_pattern(), re.I)),
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws_secret", re.compile(r"\b[A-Za-z0-9/+=]{40}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("xai_key", re.compile(r"\bxai-[A-Za-z0-9]{20,}")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}")),
    ("bearer", re.compile(r"(?i)\b(?:bearer|authorization:)\s+[A-Za-z0-9._\-]{20,}")),
    # The negative lookahead stops this matching its own replacement:
    # without it, `KEY=[REDACTED]` re-matches on the verification pass and the
    # exporter refuses to write a document that is already clean. Same bug class
    # the README scrubber hit - a redactor must not be able to redact itself.
    ("env_assignment", re.compile(
        r"(?i)\b([A-Z_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD)[A-Z_]*)"
        r"\s*=\s*(?!\[REDACTED\])\S+")),
]


def redact(text: str) -> tuple[str, dict[str, int]]:
    hits: dict[str, int] = {}
    for name, pat in REDACTIONS:
        repl = r"\1=[REDACTED]" if name == "env_assignment" else "[REDACTED]"
        text, n = pat.subn(repl, text)
        if n:
            hits[name] = hits.get(name, 0) + n
    return text, hits


def assert_clean(text: str) -> None:
    """Refuse to write if anything a redactor should have caught survives."""
    leftover, hits = redact(text)
    if hits:
        raise SystemExit(f"REFUSING TO WRITE: secrets survived redaction: {hits}")


def project_transcript_dir() -> Path:
    """The transcript directory for THIS repository, and only this one.

    Claude Code encodes the working directory into the folder name by replacing
    every non-alphanumeric character with a hyphen.
    """
    slug = "".join(c if c.isalnum() else "-" for c in str(Path.cwd()))
    return TRANSCRIPT_DIR / slug


def latest_transcript() -> Path:
    """The most complete transcript OF THIS PROJECT.

    This searched `~/.claude/projects` - every project on the machine - and took
    the most recently modified file. Working on any other repository afterwards
    made that file another project's session, and this script would have written
    it into `trajectories/build-agent.md` and published it. It did exactly that
    once during development, exporting an unrelated project's transcript into a
    submission deliverable bound for a public repository.
    
    That is a privacy leak, not a wrong-file inconvenience. So the search is
    scoped to this repository's own directory and FAILS CLOSED: if that
    directory does not exist, the script stops rather than falling back to
    whatever else is on disk.
    
    Largest rather than newest, because the build history is the point - a
    short resumed session is not the trajectory anyone wants to read.
    """
    d = project_transcript_dir()
    if not d.is_dir():
        raise SystemExit(
            f"no transcript directory for this project at {d}\n"
            f"  Refusing to fall back to other projects' transcripts.")
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_size,
                   reverse=True)
    if not files:
        raise SystemExit(f"no transcript found in {d}")
    return files[0]


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                out.append(b.get("text", ""))
        return "\n".join(out)
    return ""


def main() -> None:
    src = latest_transcript()
    lines = src.read_text(errors="replace").splitlines()
    print(f"source: {src.name}  ({len(lines):,} events)")

    md: list[str] = [
        "# Build Agent Trajectory\n",
        "The coding agent that wrote this repository: **Claude Code (Opus)**.\n",
        f"Session `{src.stem[:8]}` — {len(lines):,} recorded events.\n",
        "Every line below passed through the redactor in "
        "`scripts/export_build_trajectory.py`, which refuses to write if a known "
        "secret pattern survives.\n",
        "---\n",
    ]

    total_hits: dict[str, int] = {}
    steps = 0
    for raw in lines:
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") or {}
        role = msg.get("role") or ev.get("type")
        content = msg.get("content")

        if role == "user" and isinstance(content, str) and content.strip():
            body, hits = redact(content.strip())
            for k, v in hits.items():
                total_hits[k] = total_hits.get(k, 0) + v
            if body.startswith("<") or len(body) < 3:
                continue
            steps += 1
            md.append(f"## Human checkpoint {steps}\n")
            md.append(f"> {body[:600]}\n")

        elif role == "assistant" and isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    name = b.get("name", "?")
                    inp = json.dumps(b.get("input", {}))[:MAX_CHARS]
                    inp, hits = redact(inp)
                    for k, v in hits.items():
                        total_hits[k] = total_hits.get(k, 0) + v
                    md.append(f"**Tool call** `{name}`\n")
                    md.append(f"```json\n{inp}\n```\n")

        elif role == "user" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    body = text_of(b.get("content"))[:MAX_CHARS]
                    if not body.strip():
                        continue
                    body, hits = redact(body)
                    for k, v in hits.items():
                        total_hits[k] = total_hits.get(k, 0) + v
                    md.append("**Tool response**\n")
                    md.append(f"```\n{body}\n```\n")

    md.append("\n---\n")
    md.append(f"Redactions applied: `{total_hits or 'none'}`\n")

    doc = "\n".join(md)
    assert_clean(doc)  # post-condition: nothing sensitive survived
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(doc)
    print(f"wrote {OUT}  ({len(doc):,} chars, {steps} human checkpoints)")
    print(f"redactions: {total_hits or 'none'}")


if __name__ == "__main__":
    sys.exit(main())
