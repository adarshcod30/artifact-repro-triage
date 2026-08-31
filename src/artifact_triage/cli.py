"""`artifact-triage <owner/repo>` - produce a reviewer-ready report for one artifact.

This is the part a real user actually touches. An Artifact Evaluation reviewer is
assigned an artifact and has perhaps an hour. This gives them, in seconds, the
findings that are mechanically checkable, so their hour goes on the judgement a
human is actually needed for.

Two modes:

  --no-model   (default when no credentials are configured)
               Deterministic only. No API key, no cost, no network beyond GitHub.
               Every finding is a verified fact.

  --model      Adds the tier assessment and escalation recommendation.

The report is written to be *signed off on*: every claim cites the file or URL it
came from, uncertainty is stated rather than smoothed over, and the tool says
explicitly what it did NOT check. A reviewer who cannot see the limits of a tool
cannot responsibly use its output.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from artifact_triage.corpus.fetch import (default_branch_sha, readme,
                                          referenced_paths, signals_present, tree)
from artifact_triage.corpus.github import API, _get
from artifact_triage.corpus.scrub import scrub
from artifact_triage.solution.verify import verify

SLUG = re.compile(r"(?:github\.com[/:])?([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+?)(?:\.git)?/?$")


def parse_slug(text: str) -> str:
    m = SLUG.search(text.strip())
    if not m:
        raise SystemExit(f"could not parse a GitHub repo from: {text!r}")
    return f"{m.group(1)}/{m.group(2)}"


class RepoUnavailable(SystemExit):
    """A clean, actionable message instead of a traceback.

    A tool a reviewer runs on an unfamiliar repository will hit missing repos,
    private repos and rate limits routinely. Dumping a urllib traceback tells
    them nothing about which of those happened or what to do next.
    """


def build_factsheet(slug: str) -> dict:
    import urllib.error
    try:
        meta = _get(f"{API}/repos/{slug}", "repo-" + slug.replace("/", "__"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RepoUnavailable(
                f"'{slug}' was not found on GitHub.\n"
                f"Check the spelling, or the repository may be private or "
                f"deleted. Artifacts do disappear - that is part of what this "
                f"tool measures.")
        if exc.code in (403, 429):
            raise RepoUnavailable(
                f"GitHub rate-limited this request ({exc.code}).\n"
                f"Anonymous access allows 60 requests/hour. Set GITHUB_TOKEN, "
                f"or run `gh auth login`, for 5000/hour.")
        raise RepoUnavailable(f"GitHub returned HTTP {exc.code} for '{slug}'.")
    except urllib.error.URLError as exc:
        raise RepoUnavailable(
            f"Could not reach GitHub: {exc.reason}.\n"
            f"This command needs network access; the deterministic checks over "
            f"cached fixtures (`make verify`) do not.")
    _, sha = default_branch_sha(slug)
    entries = tree(slug, sha)
    raw = readme(slug)
    rep = scrub(raw)
    paths = [e["path"] for e in entries]
    return {
        "artifact_id": slug,
        "paper_title": meta.get("description") or "",
        "commit": sha,
        "n_files": len(paths),
        "file_tree": paths,
        "readme": rep.text[:20000],
        "readme_present": bool(raw),
        "readme_scrub": {"leaked": rep.leaked, "hits": rep.hits},
        "signals": signals_present(paths),
        "readme_referenced_paths": referenced_paths(rep.text),
        "pushed_at": meta.get("pushed_at"),
        "stars": meta.get("stargazers_count", 0),
        "archived": meta.get("archived", False),
    }


def cell(text: str) -> str:
    """Make an untrusted string safe to place in a markdown table cell.

    The report prints strings taken from other people's READMEs. Today the
    extractor cannot emit one containing "|", a newline or a backtick - it
    anchors on `^[\w./\-]+\.(ext)$` - so nothing here is reachable, and this
    is not a live defect.
    
    But that safety is an IMPLICIT COUPLING: the report is safe only because a
    regex three modules away happens to be strict, and nothing says so. Worse,
    `verify()` reads a STORED field, so a hand-edited fixture bypasses the
    extractor entirely. A newline would inject arbitrary markdown into the
    report - a fabricated heading, for instance - and a "|" would break the
    table.
    
    Escaping here costs nothing and removes the dependency on a distant
    module staying strict. A test pins the extractor's guarantee separately.
    """
    return (str(text).replace("\\", "\\\\").replace("|", "\\|")
            .replace("`", "'").replace("\r", " ").replace("\n", " "))


def _exit_code(criteria, strict: bool) -> int:
    """0 unless the caller asked for a CI gate and something was found.

    Arvan et al. (EMNLP 2022) recommend evaluating artifacts "at the time of
    publication". In practice that means a check in the author's own CI, and CI
    gates on exit codes - so without this flag the moment the literature
    identifies is not reachable. Opt-in, so plain reporting still exits 0.
    """
    if not strict:
        return 0
    # Fail only on a POSITIVE finding - something checked and found wanting.
    # A concern raised because there was nothing to check is a limit of the
    # instrument, and failing someone's build for it is a false positive.
    # Measured: that case is 17.9% of real research repositories.
    return 2 if any(c.verdict == "concerns" and not c.from_absence
                    for c in criteria) else 0


def render(fx: dict, ev, links: dict | None, model: dict | None,
           pins=None, port=None, docker=None, criteria=None) -> str:
    L: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L.append(f"# Artifact reproducibility report — `{fx['artifact_id']}`\n")
    L.append(f"Generated {now} against commit `{fx['commit']}`.\n")
    if fx.get("archived"):
        L.append("> **This repository is archived.** It will not receive fixes.\n")

    # ---- headline ----------------------------------------------------------
    problems = []
    if ev.claims_broken:
        problems.append(f"{ev.claims_broken} README path(s) that do not exist")
    if links and links["urls_dead"]:
        problems.append(f"{links['urls_dead']} dead URL(s)")
    if pins is not None:
        if pins.manifest is None:
            problems.append("no dependency manifest — environment cannot be recreated")
        elif pins.floating:
            problems.append(f"{pins.floating} unpinned dependenc"
                            f"{'y' if pins.floating == 1 else 'ies'} that will drift")
    elif not ev.has_dependency_manifest:
        problems.append("no dependency manifest")
    if port is not None and port.n:
        problems.append(f"{port.n} hard-coded machine-specific value(s)")
    if getattr(ev, "case_mismatches", None):
        problems.append(f"{len(ev.case_mismatches)} path(s) with a case "
                        f"mismatch (fail on Linux)")
    if docker is not None and docker.unpinned:
        problems.append(f"unpinned container base image "
                        f"({', '.join(docker.unpinned[:2])})")

    if problems:
        L.append(f"## Verdict: **{len(problems)} issue(s) need attention**\n")
        L += [f"- {p}" for p in problems]
    else:
        L.append("## Verdict: **no mechanical issues found**\n")
        L.append("Every checkable claim in the README resolved. "
                 "This does not mean the artifact reproduces — see *Not checked*.")
    L.append("")

    # ---- broken claims -----------------------------------------------------
    L.append("## README claims verified against the repository\n")
    L.append(f"`{ev.claims_total}` file path(s) referenced, checked against "
             f"`{fx['n_files']:,}` files at the pinned commit.\n")
    if ev.broken_paths:
        L.append("| Referenced in README | Present? | Closest real file |")
        L.append("|---|---|---|")
        for p in ev.broken_paths[:20]:
            hint = ev.suggestions.get(p)
            fix = f"`{cell(hint[0])}`" if hint else "&mdash; nothing similar"
            L.append(f"| `{cell(p)}` | **no** | {fix} |")
        if len(ev.broken_paths) > 20:
            L.append(f"\n…and {len(ev.broken_paths) - 20} more.")
        L.append("\n> Each row is a documented instruction a user would follow "
                 "and find missing.")
    elif ev.claims_total:
        L.append("All referenced paths were found.")
    else:
        L.append("The README references no checkable file paths — itself a "
                 "documentation gap, since there are no concrete instructions "
                 "to verify.")
    # Disclosed regardless of outcome: a suppression the reader cannot see is
    # worse than the false positive it hides.
    if getattr(ev, "ignored", 0):
        # State how much was hidden, not merely that something was. The party
        # being evaluated writes this file, so "1 pattern applied" is not a
        # disclosure when that pattern is `*`.
        total = ev.claims_total + ev.ignored_claims
        share = (ev.ignored_claims / total) if total else 0.0
        L.append(f"\n*{ev.ignored} author-declared exception pattern(s) from "
                 f"`.artifact-triage-ignore` suppressed **{ev.ignored_claims} of "
                 f"{total}** referenced path(s) ({share:.0%}).*")
        if ev.ignored_patterns:
            L.append("\n" + ", ".join(f"`{cell(p)}`" for p in ev.ignored_patterns[:12]))
        if share >= 0.5 and ev.ignored_claims:
            L.append(f"\n> **These exceptions suppress {share:.0%} of everything "
                     f"this check would otherwise examine.** The repository being "
                     f"assessed supplies this file, so treat the result below as "
                     f"author-filtered, not as a clean bill of health.")
    L.append("")

    # ---- links -------------------------------------------------------------
    if links:
        L.append("## External links\n")
        L.append(f"`{links['urls_checked']}` checked, "
                 f"`{links['urls_unverifiable']}` unverifiable "
                 f"(host blocks automated requests).\n")
        if links["dead_urls"]:
            L.append("Dead links:\n")
            L += [f"- `{u}`" for u in links["dead_urls"]]
        else:
            L.append("No dead links found.")
        L.append("")

    # ---- infrastructure ----------------------------------------------------
    L.append("## Reproducibility infrastructure\n")
    L.append("| Signal | Present |")
    L.append("|---|---|")
    for label, val in (("Dependency manifest", ev.has_dependency_manifest),
                       ("Container definition", ev.has_container),
                       ("Build / install script", ev.has_build_script),
                       ("CI configuration", ev.has_ci),
                       ("Tests", ev.has_tests),
                       ("Licence", ev.has_licence)):
        L.append(f"| {label} | {'yes' if val else '**no**'} |")
    L.append("")

    # ---- dependency pinning ------------------------------------------------
    if pins is not None:
        L.append("## Dependency pinning\n")
        L.append(f"{pins.summary()}\n")
        if pins.floating_examples:
            L.append("Unpinned requirements (these will resolve differently "
                     "over time):\n")
            L += [f"- `{d}`" for d in pins.floating_examples]
            L.append("")
        L.append("> Unpinned versions are the most-cited cause of artifact "
                 "decay: over 40% of 2024–25 \"functional\" artifacts fail "
                 "within months.\n")

    if docker is not None and docker.dockerfile:
        L.append("### Container\n")
        L.append(f"{docker.summary()}\n")
        if docker.unpinned:
            L.append("> An unpinned base image resolves to different software "
                     "over time — the same drift problem one layer down. "
                     "`FROM python:3.9.18` is reproducible; `FROM python` is "
                     "not.\n")

    # ---- portability -------------------------------------------------------
    if port is not None:
        L.append("## Portability\n")
        L.append(f"{port.summary()}\n")
        if port.findings:
            L.append("| File | Line | Value |")
            L.append("|---|---|---|")
            for f in port.findings[:12]:
                L.append(f"| `{f.file}` | {f.line} | `{f.excerpt[:70]}` |")
            L.append("\n> These resolve only on the machine the artifact was "
                     "written on. A reader following the documented steps will "
                     "hit them regardless of what the README says.\n")

    # ---- model assessment --------------------------------------------------
    if model:
        L.append("## Assessment\n")
        L.append(f"- **Suggested tier**: `{model.get('tier')}`")
        L.append(f"- **Confidence**: {model.get('confidence')}")
        # Always state the human's role, not only when a rule fires. Silence
        # here read as "handled automatically" while the criteria block below
        # says a reviewer is always required for Consistent - the report
        # contradicting itself.
        L.append("- **Always required of a reviewer**, whatever the rules say:")
        L.append("  - rule on `Consistent` - it needs the paper, not the files")
        L.append("  - run the artifact - no static check shows that it executes")
        if model.get("escalated"):
            L.append("- **Additionally flagged for review:**")
            for r in model.get("escalation_reasons", []):
                L.append(f"  - {cell(r)}")
        else:
            L.append("- No *additional* evidence-based rule fired.")
        if model.get("reasons"):
            L.append("\nReasoning:\n")
            L += [f"- {r}" for r in model["reasons"]]
        L.append("")

    # ---- ACM criteria ------------------------------------------------------
    if criteria:
        L.append("## ACM Functional criteria — pre-filled\n")
        from artifact_triage.solution.criteria import summary as _csum
        L.append(f"**{_csum(criteria)}**\n")
        L.append("Each finding above is evidence for or against a *named* ACM "
                 "criterion, quoted verbatim. This is the decision you have to "
                 "make anyway.\n")
        for c in criteria:
            mark = {"supported": "no mechanical concerns",
                    "concerns": "**CONCERNS**",
                    "not-checkable": "**not machine-checkable**"}[c.verdict]
            L.append(f"### {c.criterion} — {mark}\n")
            L.append(f"> *{c.definition}*\n")
            for e in c.evidence:
                # These carry the same untrusted paths ("missing: <path>"),
                # so they need the same treatment as the table cells. Escaping
                # only the table left the injection alive one section lower -
                # a reminder that untrusted data has to be tracked to EVERY
                # sink, not the first one you notice.
                L.append(f"- {cell(e)}")
            L.append(f"\n**Reviewer:** {c.needs_human}\n")

    # ---- limits ------------------------------------------------------------
    L.append("## Not checked\n")
    L.append("This tool verifies that documented *references* resolve. It does "
             "**not**:\n")
    L.append("- run the code, or verify that it produces the paper's results")
    L.append("- check that the pinned dependency versions actually still install")
    L.append("- validate semantic claims (\"reproduces Table 3\", \"tested on "
             "Ubuntu 22.04\")")
    L.append("- assess scientific correctness\n")
    L.append("An artifact can pass every check here and still fail to "
             "reproduce. This narrows where a reviewer looks; it does not "
             "replace the reviewer.")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="artifact-triage",
        description="Reproducibility report for a research artifact repository.")
    ap.add_argument("repo", help="owner/repo or a GitHub URL")
    ap.add_argument("--model", action="store_true",
                    help="also produce a tier assessment (needs credentials)")
    ap.add_argument("--no-links", action="store_true",
                    help="skip URL checking (offline)")
    ap.add_argument("--fail-on-findings", action="store_true",
                    help="exit non-zero if any mechanical check raises a "
                         "concern (for CI, so a broken README fails a build)")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable findings instead of the report")
    ap.add_argument("-o", "--out", help="write the report to a file")
    args = ap.parse_args(argv)

    slug = parse_slug(args.repo)
    print(f"fetching {slug} …", file=sys.stderr)
    fx = build_factsheet(slug)
    if not fx["readme_present"]:
        print("warning: this repository has no README", file=sys.stderr)
    from artifact_triage.solution.pinning import fetch_file
    from artifact_triage.solution.verify import load_ignores
    ignores = load_ignores(fx["file_tree"], fetch=fetch_file, slug=slug)
    ev = verify(fx, ignores=ignores)

    from artifact_triage.solution.pinning import analyse as analyse_pins
    pins = analyse_pins(slug, fx["file_tree"])

    from artifact_triage.solution.pinning import analyse_docker
    docker = analyse_docker(slug, fx["file_tree"])

    from artifact_triage.solution.portability import inspect as inspect_port
    print("scanning for environment leakage …", file=sys.stderr)
    port = inspect_port(slug, fx["file_tree"])

    links = None
    if not args.no_links:
        from artifact_triage.solution.links import for_artifact
        print("checking links …", file=sys.stderr)
        links = for_artifact(slug, fx["readme"])

    model = None
    if args.model:
        from artifact_triage.common.llm import ask, client
        from artifact_triage.common.rubric import RUBRIC
        from artifact_triage.solution.run import ESCALATE_BELOW, prompt_for
        print("asking the model …", file=sys.stderr)
        a = ask(client(), RUBRIC, prompt_for(fx))
        from artifact_triage.solution.escalate import decide
        d = decide(ev, a.tier, a.confidence, fx.get("readme_present", True))
        model = {"tier": a.tier, "confidence": a.confidence,
                 "reasons": a.reasons, "escalated": d.escalate,
                 "escalation_reasons": d.reasons}

    from artifact_triage.solution.criteria import assess
    from artifact_triage.solution.criteria import summary as criteria_summary
    criteria = assess(ev, pins=pins, docker=docker, port=port, links=links)

    # Machine-readable output exists because the product thesis is reviewer
    # CAPACITY. A chair triaging a venue's worth of artifacts needs a sortable
    # record per repository, not prose to read one at a time. Every report
    # dataclass already had a `to_dict`; nothing consumed them, because the
    # output mode they were written for had never been built.
    if args.json:
        payload = {
            "artifact_id": fx["artifact_id"],
            "commit": fx.get("commit"),
            "readme_present": fx["readme_present"],
            "verified": ev.to_dict(),
            "pinning": pins.to_dict() if pins else None,
            "container": docker.to_dict() if docker else None,
            "portability": port.to_dict() if port else None,
            "links": links,
            "model": model,
            "acm_functional": [c.to_dict() for c in criteria],
            "acm_summary": criteria_summary(criteria),
        }
        text = json.dumps(payload, indent=1)
        if args.out:
            Path(args.out).write_text(text)
            print(f"-> {args.out}", file=sys.stderr)
        else:
            print(text)
        return _exit_code(criteria, args.fail_on_findings)

    report = render(fx, ev, links, model, pins, port, docker, criteria)
    if args.out:
        Path(args.out).write_text(report)
        print(f"-> {args.out}", file=sys.stderr)
    else:
        print(report)
    return _exit_code(criteria, args.fail_on_findings)


if __name__ == "__main__":
    raise SystemExit(main())
