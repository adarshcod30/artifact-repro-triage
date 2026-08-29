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


def build_factsheet(slug: str) -> dict:
    meta = _get(f"{API}/repos/{slug}", "repo-" + slug.replace("/", "__"))
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


def render(fx: dict, ev, links: dict | None, model: dict | None,
           pins=None, port=None, docker=None) -> str:
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
            fix = f"`{hint[0]}`" if hint else "&mdash; nothing similar"
            L.append(f"| `{p}` | **no** | {fix} |")
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
        L.append(f"\n*{ev.ignored} author-declared exception pattern(s) applied "
                 f"from `.artifact-triage-ignore`.*")
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
        if model.get("escalated"):
            L.append("- **Recommendation: route to a human reviewer.**")
            for r in model.get("escalation_reasons", []):
                L.append(f"  - {r}")
        if model.get("reasons"):
            L.append("\nReasoning:\n")
            L += [f"- {r}" for r in model["reasons"]]
        L.append("")

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

    report = render(fx, ev, links, model, pins, port, docker)
    if args.out:
        Path(args.out).write_text(report)
        print(f"-> {args.out}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
