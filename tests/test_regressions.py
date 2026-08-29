"""Regression tests pinning every bug the changelog claims to have fixed.

A changelog entry is a claim. These tests make each one enforceable: if a fix is
ever undone, a test fails and names the original defect. Every test below
corresponds to a real bug found during development, not a hypothetical.

Run with:  make test
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artifact_triage.corpus.fetch import _is_path, referenced_paths  # noqa: E402
from artifact_triage.corpus.scrub import scrub  # noqa: E402
from artifact_triage.corpus.zenodo import github_repos, normalise  # noqa: E402
from artifact_triage.eval.metrics import Prediction, score  # noqa: E402
from artifact_triage.solution.criteria import ACM, assess  # noqa: E402
from artifact_triage.solution.verify import _index, check_claim, verify  # noqa: E402


# --------------------------------------------------------------------------
# Iteration 13 - "a dot does not make a path"
# The extractor matched any token containing a dot, sweeping up version
# numbers, Java class names, module paths and bare domains. 55 of 58 "broken
# claims" on one artifact were extraction noise.
# --------------------------------------------------------------------------
def test_version_numbers_are_not_paths():
    for tok in ("3.10.12", "0.01", "7.612486", "1.0.0", "gpt-3.5"):
        assert not _is_path(tok), f"{tok!r} must not be treated as a file path"


def test_dotted_identifiers_are_not_paths():
    for tok in ("com.baidu.jprotobuf.EchoServiceTest.testDy",
                "vllm.entrypoints.openai.api",
                "backend.type"):
        assert not _is_path(tok), f"{tok!r} is an identifier, not a path"


def test_bare_domains_are_not_paths():
    assert not _is_path("github.com")
    assert not _is_path("example.org")


def test_real_paths_are_still_recognised():
    for tok in ("scripts/run.py", "requirements.txt", "src/main.c",
                "configs/base.yaml", "Makefile.am"):
        assert _is_path(tok), f"{tok!r} should be recognised as a path"


# --------------------------------------------------------------------------
# Iteration 20 - fenced-code-block pairing
# Claims inside a ```bash block were silently dropped when an upstream fence
# was mismatched, because the regex paired delimiters positionally.
# --------------------------------------------------------------------------
def test_claims_inside_code_fences_are_extracted():
    readme = (
        "# Project\n\n```\nunclosed fence above\n\n"
        "## Run\n\n```bash\nbash scripts/run_experiments.sh\n"
        "python src/train_model.py\n```\n"
    )
    found = referenced_paths(readme)
    assert "scripts/run_experiments.sh" in found
    assert "src/train_model.py" in found


# --------------------------------------------------------------------------
# Iteration 19 - a parent directory existing does not satisfy a FILE claim.
# This rule alone accounted for every miss at 84% detection.
# --------------------------------------------------------------------------
def test_existing_directory_does_not_satisfy_a_file_claim():
    tree = ["scripts/other.py", "scripts/helper.py"]
    exact, base, dirs = _index(tree)
    c = check_claim("scripts/run_experiments.sh", exact, base, dirs)
    assert not c.exists, "a missing file must not pass because its folder exists"


def test_directory_claim_is_satisfied_by_the_directory():
    tree = ["configs/a.yaml"]
    exact, base, dirs = _index(tree)
    assert check_claim("configs", exact, base, dirs).exists


def test_exact_and_basename_matches_still_work():
    tree = ["src/train.py", "requirements.txt"]
    exact, base, dirs = _index(tree)
    assert check_claim("requirements.txt", exact, base, dirs).exists
    assert check_claim("train.py", exact, base, dirs).exists  # basename match


# --------------------------------------------------------------------------
# Iterations 7-8 - the scrubber must not be able to redact itself, and no
# tier word may survive. The first version produced [REDACTED:[REDACTED:BADGE]]
# and left `.../badge/artifact-reusable-green` fully readable.
# --------------------------------------------------------------------------
def test_no_tier_word_survives_scrubbing():
    samples = [
        "This artifact received the **Artifacts Evaluated - Reusable** badge.",
        "![ACM Badge](https://img.shields.io/badge/artifact-reusable-green)",
        "Our results were reproduced by the Artifact Evaluation Committee.",
        "The artifact is Reusable and well documented.",
        "[![badge](https://img.shields.io/badge/ACM-Functional-blue)](https://acm.org)",
    ]
    for text in samples:
        out = scrub(text).text
        low = out.lower()
        assert "reusable" not in low and "functional" not in low, \
            f"tier word survived scrubbing: {out!r}"


def test_redaction_is_not_itself_redactable():
    once = scrub("Artifacts Evaluated - Reusable badge").text
    twice = scrub(once).text
    assert once == twice, "scrubbing must be idempotent, not self-matching"


def test_ordinary_readme_text_is_untouched():
    text = "Run `python main.py --seed 0` to reproduce Table 2."
    assert scrub(text).text == text


# --------------------------------------------------------------------------
# Bugfix - rstrip(".git") strips CHARACTERS, not a suffix, so "upbeat"
# became "upbea". It broke 2 of 15 repository slugs.
# --------------------------------------------------------------------------
def test_git_suffix_stripping_does_not_eat_real_characters():
    record = {"metadata": {"x": "https://github.com/NWU-NISL-Fuzzing/upbeat"}}
    assert github_repos(record) == ["NWU-NISL-Fuzzing/upbeat"]


def test_git_suffix_is_actually_removed():
    record = {"metadata": {"x": "https://github.com/owner/name.git"}}
    assert github_repos(record) == ["owner/name"]


def test_zenodo_title_normalisation_strips_decoration():
    a = normalise('Artifact of [ISSTA\'24] "A Large-Scale Evaluation"')
    b = normalise("A Large-Scale Evaluation")
    assert b in a


# --------------------------------------------------------------------------
# Iteration 16 - file trees must not be truncated, or real paths are reported
# as broken. 4 of 15 fixtures were affected and they were exactly the outliers.
# --------------------------------------------------------------------------
def test_fixtures_have_complete_file_trees():
    import json
    fixtures = list(Path("data/fixtures").glob("*.json"))
    assert fixtures, "no fixtures found - run make corpus"
    for p in fixtures:
        fx = json.loads(p.read_text())
        assert len(fx["file_tree"]) == fx["n_files"], (
            f"{fx['artifact_id']}: file_tree truncated "
            f"({len(fx['file_tree'])} of {fx['n_files']}) - path checks would "
            f"report false broken claims")


# --------------------------------------------------------------------------
# Iteration 25 - the floor effect. An artifact already at the lowest tier
# cannot be downgraded, so it must not be counted as a detection failure.
# --------------------------------------------------------------------------
def test_scorer_separates_escalation_from_failure():
    labels = {"a": "Reusable", "b": "Available"}
    preds = [Prediction("a", None, 0.2, escalated=True),
             Prediction("b", "Available", 0.9)]
    r = score("s", preds, labels, 1.0, 1.0)
    assert r.n_escalated == 1
    assert r.n_failed == 0, "an escalation is a human handoff, not a failure"
    assert r.n_scored == 1


def test_overclaim_is_tracked_separately_from_mae():
    labels = {"a": "Available", "b": "Reusable"}
    # One overclaim (Available -> Reusable) and one underclaim, equal |error|.
    preds = [Prediction("a", "Reusable", 0.9), Prediction("b", "Available", 0.9)]
    r = score("s", preds, labels, 1.0, 1.0)
    assert r.mae == 2.0
    assert r.overclaim_rate == 0.5, "the unsafe direction must be visible"


# --------------------------------------------------------------------------
# Dependency pinning - a vendored manifest six levels deep is not the
# artifact's own manifest. Selecting one inflated the pinned ratio.
# --------------------------------------------------------------------------
def test_vendored_manifest_is_not_selected():
    from artifact_triage.solution.pinning import _shallowest, LOCKFILES
    tree = ["FF_AFL++/frida_mode/ts/package-lock.json", "src/main.c"]
    assert _shallowest(tree, LOCKFILES) is None, \
        "a manifest 3+ levels deep is vendored code, not the artifact's own"


def test_root_manifest_is_selected_over_nested():
    from artifact_triage.solution.pinning import _shallowest, PY_MANIFESTS
    tree = ["deep/nested/dir/requirements.txt", "requirements.txt"]
    assert _shallowest(tree, PY_MANIFESTS) == "requirements.txt"


def test_pinned_and_floating_are_classified_correctly():
    from artifact_triage.solution.pinning import classify_requirements
    text = ("torch==2.1.0\n"          # pinned
            "numpy\n"                 # floating
            "hydra-core>=1.1.0\n"     # floating (lower bound only)
            "pandas>=1.0,<2.0\n"      # bounded
            "# a comment\n"
            "-r other.txt\n")         # option line, not a requirement
    pinned, bounded, floating, _ = classify_requirements(text)
    assert (pinned, bounded, floating) == (1, 1, 2)


# --------------------------------------------------------------------------
# Portability - only near-certainly non-portable values are reported.
# Over-reporting would train a reviewer to ignore the output.
# --------------------------------------------------------------------------
def test_conventional_paths_are_not_flagged():
    from artifact_triage.solution.portability import scan_text
    text = "import os\npath = '/usr/bin/python'\ntmp = '/tmp/scratch'\n"
    assert scan_text(text, "a.py") == []


def test_user_home_paths_are_flagged():
    from artifact_triage.solution.portability import scan_text
    found = scan_text("data = '/home/alice/project/train.csv'", "a.py")
    assert len(found) == 1 and found[0].kind == "absolute_home_path"


def test_private_network_addresses_are_flagged():
    from artifact_triage.solution.portability import scan_text
    found = scan_text("HOST = '192.168.1.42'", "conf.py")
    assert found and found[0].kind == "private_host"


def test_public_ip_like_versions_are_not_flagged():
    from artifact_triage.solution.portability import scan_text
    assert scan_text("version = '8.8.8.8'", "a.py") == []


# --------------------------------------------------------------------------
# Container base images drift exactly like unpinned pip requirements.
# --------------------------------------------------------------------------
def _fake_docker(content):
    return lambda slug, path: content


def test_unpinned_base_image_is_flagged():
    from artifact_triage.solution.pinning import analyse_docker
    d = analyse_docker("o/r", ["Dockerfile"],
                       fetch=_fake_docker("FROM python\nRUN pip install x\n"))
    assert d.unpinned == ["python"]


def test_latest_tag_is_unpinned():
    from artifact_triage.solution.pinning import analyse_docker
    d = analyse_docker("o/r", ["Dockerfile"],
                       fetch=_fake_docker("FROM ubuntu:latest\n"))
    assert d.unpinned == ["ubuntu:latest"]


def test_version_tag_and_digest_count_as_pinned():
    from artifact_triage.solution.pinning import analyse_docker
    d = analyse_docker("o/r", ["Dockerfile"],
                       fetch=_fake_docker("FROM python:3.9.18\n"))
    assert d.unpinned == []
    d2 = analyse_docker("o/r", ["Dockerfile"],
                        fetch=_fake_docker("FROM python@sha256:abc123\n"))
    assert d2.unpinned == []


def test_multistage_build_aliases_are_stripped():
    from artifact_triage.solution.pinning import analyse_docker
    d = analyse_docker("o/r", ["Dockerfile"],
                       fetch=_fake_docker("FROM python:3.11 AS builder\n"
                                          "FROM debian:12 AS runtime\n"))
    assert d.base_images == ["python:3.11", "debian:12"]
    assert d.unpinned == []


# --------------------------------------------------------------------------
# Suggestions - a report that only says "wrong" leaves the author hunting.
# Most broken claims are near-misses, so the fix is one path away.
# --------------------------------------------------------------------------
_TREE = ["src/train_model.py", "scripts/run_experiment.sh",
         "configs/base.yaml", "README.md"]


def test_moved_file_is_suggested_by_basename():
    from artifact_triage.solution.verify import suggest
    assert suggest("train_model.py", _TREE) == ["src/train_model.py"]


def test_pluralisation_typo_is_suggested():
    from artifact_triage.solution.verify import suggest
    assert suggest("scripts/run_experiments.sh", _TREE)[0] == \
        "scripts/run_experiment.sh"
    assert suggest("config/base.yaml", _TREE)[0] == "configs/base.yaml"


def test_unrelated_path_gets_no_suggestion():
    from artifact_triage.solution.verify import suggest
    assert suggest("totally/unrelated.py", _TREE) == []


def test_extension_mismatch_is_not_suggested():
    from artifact_triage.solution.verify import suggest
    # A .py claim must not be answered by a same-stemmed .md file.
    assert suggest("base.py", ["configs/base.yaml", "docs/base.md"]) == []


# --------------------------------------------------------------------------
# Declared exceptions. Found by dogfooding: our own README quotes other
# artifacts' paths. Suppression must be explicit and must be reported.
# --------------------------------------------------------------------------
def _fx(paths, refs):
    return {"artifact_id": "o/r", "file_tree": paths, "n_files": len(paths),
            "readme": "x", "readme_referenced_paths": refs, "signals": {}}


def test_declared_exception_suppresses_a_claim():
    fx = _fx(["a.py"], ["other/project.py"])
    assert verify(fx).claims_broken == 1
    assert verify(fx, ignores=["other/*"]).claims_broken == 0


def test_suppression_count_is_always_reported():
    fx = _fx(["a.py"], ["other/project.py"])
    ev = verify(fx, ignores=["other/*"])
    assert ev.ignored == 1, "a silent suppression is worse than a false positive"
    assert "exception pattern" in ev.as_prompt_block()


def test_ignores_do_not_suppress_unrelated_claims():
    fx = _fx(["a.py"], ["other/project.py", "missing/real.py"])
    assert verify(fx, ignores=["other/*"]).claims_broken == 1


def test_ignore_file_parsing_skips_comments_and_blanks():
    from artifact_triage.solution.verify import load_ignores, IGNORE_FILE
    body = "# a comment\n\nscripts/x.py\ny.py  # trailing\n"
    got = load_ignores([IGNORE_FILE], fetch=lambda s, p: body, slug="o/r")
    assert got == ["scripts/x.py", "y.py"]


# --------------------------------------------------------------------------
# Escalation - the confidence gate fired 0/15 and was anti-calibrated
# (0.700 mean confidence when right, 0.750 when wrong). Evidence decides.
# --------------------------------------------------------------------------
def test_reusable_verdict_contradicting_evidence_escalates():
    from artifact_triage.solution.escalate import decide
    fx = _fx(["a.py"], [f"missing{i}.py" for i in range(10)])
    d = decide(verify(fx), "Reusable", 0.95)
    assert d.escalate
    assert any("contradicts the evidence" in r for r in d.reasons)


def test_functional_verdict_contradicting_evidence_also_escalates():
    """ACM defines Functional as 'documented, consistent, complete'. A
    Functional verdict over a third of missing paths is as contradictory as a
    Reusable one. The rule originally required Reusable and so never fired -
    the model does not use that tier on this corpus."""
    from artifact_triage.solution.escalate import decide
    fx = _fx(["a.py"], [f"missing{i}.py" for i in range(10)])
    d = decide(verify(fx), "Functional", 0.95)
    assert d.escalate
    assert any("contradicts the evidence" in r for r in d.reasons)


def test_contradiction_rule_does_not_fire_on_clean_evidence():
    from artifact_triage.solution.escalate import decide
    fx = _fx(["a.py", "b.py", "c.py", "d.py", "req.txt"],
             ["a.py", "b.py", "c.py", "d.py"])
    d = decide(verify(fx), "Functional", 0.5)
    assert not any("contradicts" in r for r in d.reasons), \
        "a clean artifact must not trip the contradiction guard"


def test_no_checkable_claims_escalates():
    from artifact_triage.solution.escalate import decide
    fx = _fx(["a.py"], [])
    fx["readme"] = "x" * 900   # long enough not to trip the thin-README rule
    d = decide(verify(fx), "Functional", 0.99)
    assert d.escalate
    assert any("no checkable file references" in r for r in d.reasons)


def test_high_confidence_alone_never_prevents_escalation():
    from artifact_triage.solution.escalate import decide
    fx = _fx(["a.py"], [])
    assert decide(verify(fx), "Functional", 1.0).escalate, \
        "self-reported confidence must not override the evidence"


def test_report_never_contradicts_its_own_evidence():
    """The report listed 5 missing paths then said 'All referenced paths were
    found' - a claim contradicted by its own table, which is the exact defect
    this project detects."""
    from artifact_triage.cli import render
    fx = {"artifact_id": "o/r", "commit": "abc", "n_files": 10,
          "file_tree": ["a.py"], "readme": "x",
          "readme_referenced_paths": ["gone.py"], "signals": {}}
    ev = verify(fx)
    assert ev.claims_broken == 1
    out = render(fx, ev, None, None)
    assert "All referenced paths were found" not in out


# --------------------------------------------------------------------------
# Our own documentation must not reference things that do not exist. The
# README's table of contents shipped two anchors that resolved to nothing -
# the same defect class the tool detects, in the tool's own README.
# --------------------------------------------------------------------------
def test_readme_toc_anchors_all_resolve():
    import re
    src = Path(__file__).resolve().parents[1] / "README.md"
    if not src.exists():
        return
    text = src.read_text()
    body = re.sub(r"```.*?```", "", text, flags=re.S)  # ignore example output

    def slug(h: str) -> str:
        h = re.sub(r"[^\w\s-]", "", h.lower())
        return re.sub(r"\s", "-", h.strip())

    have = {slug(h) for h in re.findall(r"^#{1,4} (.+)$", body, re.M)}
    bad = [a for a in re.findall(r"\]\(#([^)]+)\)", text) if a not in have]
    assert not bad, f"README links to non-existent anchors: {bad}"


def test_readme_relative_links_point_at_real_files():
    import re
    root = Path(__file__).resolve().parents[1]
    text = (root / "README.md").read_text()
    targets = re.findall(r"\]\((?!https?://|#)([^)\s]+)\)", text)
    missing = [t for t in targets if not (root / t.split("#")[0]).exists()]
    assert not missing, f"README links to missing files: {missing}"


# --------------------------------------------------------------------------
# FAIRNESS INVARIANT. The entire comparison rests on the baseline receiving
# the same task and the same README, and NO verified evidence. If that ever
# stops holding, the measured improvement means nothing.
# --------------------------------------------------------------------------
def _one_fixture():
    import json
    fs = sorted(Path("data/fixtures").glob("*.json"))
    return json.loads(fs[0].read_text()) if fs else None


def test_baseline_prompt_contains_no_verified_evidence():
    fx = _one_fixture()
    if fx is None:
        return
    import os
    os.environ["ARTIFACT_TRIAGE_FULL_EVIDENCE"] = "0"  # keep this test offline
    from artifact_triage.baseline.run import prompt_for as bp
    text = bp(fx)
    for marker in ("VERIFIED", "MISSING:", "do NOT exist",
                   "Environment reproducibility", "Portability"):
        assert marker not in text, (
            f"baseline prompt leaked verified evidence ({marker!r}) - the "
            f"comparison would no longer be attributable")


def test_both_systems_receive_the_same_readme():
    fx = _one_fixture()
    if fx is None:
        return
    import os
    os.environ["ARTIFACT_TRIAGE_FULL_EVIDENCE"] = "0"
    from artifact_triage.baseline.run import prompt_for as bp
    from artifact_triage.solution.run import prompt_for as sp
    readme = fx["readme"][:400]
    assert readme in bp(fx) and readme in sp(fx), \
        "both systems must see the identical README text"


def test_both_systems_share_one_rubric():
    from artifact_triage.common.rubric import RUBRIC
    import artifact_triage.baseline.run as b
    import artifact_triage.solution.run as s
    assert b.RUBRIC is RUBRIC and s.RUBRIC is RUBRIC, \
        "a divergent rubric would change the task, not just the evidence"


# --------------------------------------------------------------------------
# Spend must be append-only. The first version summed the cost fields in
# results/*.json, so a re-run overwrote its file and the previous run's cost
# vanished - it reported $0.49 against a true $1.12. Under-reporting against a
# hard budget is the worst direction to be wrong.
# --------------------------------------------------------------------------
def test_ledger_accumulates_across_reruns(tmp_path=None):
    import importlib
    from artifact_triage.common import ledger
    orig = ledger.LEDGER
    try:
        import tempfile
        d = Path(tempfile.mkdtemp())
        ledger.LEDGER = d / "l.jsonl"
        ledger.record("falsified", 0.40, 180)
        ledger.record("falsified", 0.40, 180)   # a re-run of the SAME kind
        assert abs(ledger.total() - 0.80) < 1e-9, \
            "a re-run must add to the total, never replace it"
    finally:
        ledger.LEDGER = orig


def test_ledger_reports_threshold_crossings():
    from artifact_triage.common import ledger
    orig = ledger.LEDGER
    try:
        import tempfile
        d = Path(tempfile.mkdtemp())
        ledger.LEDGER = d / "l.jsonl"
        ledger.record("x", 0.9, 1)
        assert ledger.crossed() == []
        ledger.record("x", 0.2, 1)
        assert ledger.crossed() == [1.0]
    finally:
        ledger.LEDGER = orig


# --------------------------------------------------------------------------
# The video has a hard 5-minute cap. A script that overruns or overlaps is a
# documented plan that does not work - checkable, so it is checked.
# --------------------------------------------------------------------------
def test_video_script_timings_are_consistent():
    import re
    p = Path(__file__).resolve().parents[1] / "docs/VIDEO_SCRIPT.md"
    if not p.exists():
        return
    segs = re.findall(r"^## (\d):(\d\d) – (\d):(\d\d)", p.read_text(), re.M)
    assert segs, "no timed segments found"
    prev_end = 0
    for a, b, c, d in segs:
        start, end = int(a) * 60 + int(b), int(c) * 60 + int(d)
        assert start >= prev_end, f"segment {a}:{b} overlaps the previous one"
        assert end > start, f"segment {a}:{b}-{c}:{d} ends before it starts"
        prev_end = end
    assert prev_end <= 300, f"script runs to {prev_end}s, over the 5:00 cap"


# --------------------------------------------------------------------------
# A reviewer running this on an unfamiliar repository will hit missing repos,
# private repos and rate limits routinely. A urllib traceback tells them
# nothing about which happened or what to do next.
# --------------------------------------------------------------------------
def test_missing_repo_gives_an_actionable_message_not_a_traceback():
    import urllib.error
    from artifact_triage import cli

    def boom(url, key):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    orig = cli._get
    try:
        cli._get = boom
        try:
            cli.build_factsheet("nope/nope")
            assert False, "should have raised"
        except cli.RepoUnavailable as e:
            msg = str(e)
            assert "not found" in msg.lower()
            assert "private or" in msg.lower(), "should explain the likely causes"
    finally:
        cli._get = orig


def test_rate_limit_message_names_the_fix():
    import urllib.error
    from artifact_triage import cli

    def boom(url, key):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    orig = cli._get
    try:
        cli._get = boom
        try:
            cli.build_factsheet("a/b")
            assert False, "should have raised"
        except cli.RepoUnavailable as e:
            assert "GITHUB_TOKEN" in str(e), "must tell the user how to fix it"
    finally:
        cli._get = orig


def test_url_and_git_suffix_forms_parse_to_the_same_slug():
    from artifact_triage.cli import parse_slug
    for form in ("psf/black", "psf/black.git", "https://github.com/psf/black",
                 "https://github.com/psf/black.git", "git@github.com:psf/black"):
        assert parse_slug(form) == "psf/black", form


# --------------------------------------------------------------------------
# A mermaid block with unbalanced brackets renders as a raw error box on
# GitHub - a broken figure in the document that argues for checking figures.
# --------------------------------------------------------------------------
def test_mermaid_diagrams_are_well_formed():
    import re
    src = Path(__file__).resolve().parents[1] / "README.md"
    if not src.exists():
        return
    for block in re.findall(r"```mermaid\n(.*?)```", src.read_text(), re.S):
        assert block.count("subgraph") == len(
            re.findall(r"^\s*end\s*$", block, re.M)), "unclosed subgraph"
        for o, c in (("[", "]"), ("(", ")"), ("{", "}")):
            assert block.count(o) == block.count(c), f"unbalanced {o}{c}"


# --------------------------------------------------------------------------
# Directory references are claims too. Found by auditing for FALSE NEGATIVES -
# 64 backtick-quoted directory paths were being silently skipped. A missed
# claim is invisible by definition, so nothing had ever checked for them.
# --------------------------------------------------------------------------
def test_explicit_directory_references_are_claims():
    from artifact_triage.corpus.fetch import _is_dir_ref
    for tok in ("reproduction/", "replication/", "src/main/", "docs/api/v2/"):
        assert _is_dir_ref(tok), tok


def test_shell_and_variable_tokens_are_not_directory_claims():
    from artifact_triage.corpus.fetch import _is_dir_ref
    # A checker that reports variable names as missing directories gets ignored.
    for tok in ("CC/CXX", "ff-all-in-one/++", "$(pwd)/bugs/", "http://x/",
                "a/", "/etc/", "-flag/"):
        assert not _is_dir_ref(tok), tok


def test_directory_without_trailing_slash_is_not_assumed():
    from artifact_triage.corpus.fetch import _is_dir_ref
    assert not _is_dir_ref("some/path"), \
        "without an explicit slash this is ambiguous with a file"


# --------------------------------------------------------------------------
# A staleness detector with a blind spot is worse than none: it certifies the
# thing it cannot see. fetch.py decides which claims exist at all, so it
# influences every result.
# --------------------------------------------------------------------------
def test_every_result_kind_tracks_the_extractor():
    from artifact_triage.common.provenance import INFLUENCERS
    for kind, files in INFLUENCERS.items():
        assert "src/artifact_triage/corpus/fetch.py" in files, (
            f"'{kind}' does not track fetch.py, so a change to the extractor "
            f"would leave its results looking current")


def test_fingerprint_changes_when_influencing_code_changes():
    from artifact_triage.common import provenance
    before = provenance.fingerprint("verify")
    orig = provenance.INFLUENCERS["verify"]
    try:
        provenance.INFLUENCERS["verify"] = orig + ["README.md"]
        assert provenance.fingerprint("verify") != before
    finally:
        provenance.INFLUENCERS["verify"] = orig


# --------------------------------------------------------------------------
# PRECISION AUDIT. Hand-checking reported findings against real repositories
# showed precision was 78%, not the ~100% the negative control implied - the
# control only ever tested claims we injected, which are perfect by
# construction. Three false-positive classes were responsible.
# --------------------------------------------------------------------------
def test_placeholder_paths_are_not_claims():
    from artifact_triage.solution.verify import interesting
    for tok in ("path/to/data.csv", "TMP_DIR/funcid.csv", "YOUR_PATH/x.py",
                "<name>/config.yaml", "$HOME/run.sh", "example/foo.py"):
        assert not interesting(tok), f"{tok} is a placeholder, not a claim"


def test_runtime_output_dirs_are_not_claims():
    from artifact_triage.solution.verify import interesting
    for tok in ("out", "logs", "results", "build", "testdata", "node_modules"):
        assert not interesting(tok), f"{tok} is created by running the tool"


def test_a_file_inside_an_output_dir_is_still_a_claim():
    from artifact_triage.solution.verify import interesting
    assert interesting("results/table3.csv"), \
        "only BARE directory names are runtime output; concrete files are claims"


def test_case_mismatch_is_reported_separately_from_missing():
    fx = _fx(["README.md"], ["README.MD"])
    ev = verify(fx)
    assert ev.claims_broken == 0, "the file exists - it is not missing"
    assert ev.case_mismatches == ["README.MD"], \
        "but it fails on Linux, so it must still be reported"
    assert "CASE MISMATCH" in ev.as_prompt_block()


# --------------------------------------------------------------------------
# Response parsing. A greedy brace match spans from the first { to the last,
# which is invalid whenever a model emits more than one object. Llama 3.3
# echoes the JSON schema before its answer; every such response was recorded
# as an unparseable failure, making the model look 10x worse than it is.
# --------------------------------------------------------------------------
def test_schema_echoed_before_answer_is_parsed():
    from artifact_triage.common.llm import _parse
    raw = ('{"type": "object", "properties": {"tier": {"type": "string"}}}\n\n'
           '{"tier": "Functional", "confidence": 0.8, "reasons": ["a"]}')
    a = _parse(raw, 0, 0)
    assert a.tier == "Functional" and a.confidence == 0.8, \
        "the schema must not be mistaken for the answer"


def test_plain_and_fenced_objects_still_parse():
    from artifact_triage.common.llm import _parse
    assert _parse('{"tier":"Reusable","confidence":0.9,"reasons":[]}', 0, 0).tier \
        == "Reusable"
    assert _parse('```json\n{"tier":"Available","confidence":0.5,"reasons":[]}\n```',
                  0, 0).tier == "Available"


def test_braces_inside_strings_do_not_break_scanning():
    from artifact_triage.common.llm import _parse
    raw = '{"tier":"Functional","confidence":0.7,"reasons":["uses {placeholder}"]}'
    assert _parse(raw, 0, 0).tier == "Functional"


def test_genuinely_unparseable_output_is_reported_as_such():
    from artifact_triage.common.llm import _parse
    a = _parse("I think this artifact is probably functional.", 0, 0)
    assert a.tier is None and a.error == "unparseable response"


# --------------------------------------------------------------------------
# End-to-end: the verifier is deterministic. Same input, same output, always.
# --------------------------------------------------------------------------
def test_verifier_is_deterministic():
    import json
    p = sorted(Path("data/fixtures").glob("*.json"))
    if not p:
        return
    fx = json.loads(p[0].read_text())
    a, b = verify(fx), verify(fx)
    assert a.to_dict() == b.to_dict()


# --------------------------------------------------------------------------
# Iteration 74 - ACM badge-criteria mapping
#
# These are not bug regressions. They pin the HONESTY of the mapping: the
# value of reporting against named ACM criteria depends entirely on never
# overclaiming which of them a machine can settle. A future edit that quietly
# marks `Consistent` as mechanically checkable would make the whole report
# untrustworthy while still passing every other test in this file.
# --------------------------------------------------------------------------
def _fake_evidence(**kw):
    class E:
        readme_bytes = 2000
        claims_total = 10
        claims_broken = 0
        broken_paths: list = []
        has_build_script = True
    e = E()
    e.broken_paths = []
    for k, v in kw.items():
        setattr(e, k, v)
    return e


def test_consistent_is_never_claimed_as_machine_checkable():
    """The criterion requiring the paper must always be escalated."""
    for ev in (_fake_evidence(),
               _fake_evidence(claims_broken=9, broken_paths=["a.py"] * 9),
               _fake_evidence(readme_bytes=0, claims_total=0)):
        c = [f for f in assess(ev) if f.criterion == "Consistent"][0]
        assert c.mechanical is False
        assert c.verdict == "not-checkable"


def test_all_four_functional_qualities_are_covered_exactly_once():
    names = [f.criterion for f in assess(_fake_evidence())]
    assert sorted(names) == sorted(ACM)
    assert len(names) == len(set(names)) == 4


def test_broken_paths_are_evidence_against_completeness():
    ev = _fake_evidence(claims_broken=5, broken_paths=["scripts/run.sh"])
    comp = [f for f in assess(ev) if f.criterion == "Complete"][0]
    assert comp.verdict == "concerns"
    assert any("scripts/run.sh" in e for e in comp.evidence)


def test_resolving_paths_do_not_raise_completeness_concerns():
    comp = [f for f in assess(_fake_evidence()) if f.criterion == "Complete"][0]
    assert comp.verdict == "supported"


def test_exercisable_never_claims_the_artifact_runs():
    """Static checks give a necessary condition only. Say so, always."""
    for ev in (_fake_evidence(), _fake_evidence(claims_broken=3)):
        ex = [f for f in assess(ev) if f.criterion == "Exercisable"][0]
        assert "Run it" in ex.needs_human


def test_criteria_definitions_are_verbatim_not_paraphrased():
    """Paraphrasing ACM would let the tool grade against its own invention."""
    assert ACM["Complete"] == ("To the extent possible, all components relevant "
                               "to the paper in question are included.")
    assert ACM["Consistent"].startswith("The artifacts are relevant to the "
                                        "associated paper")
    for f in assess(_fake_evidence()):
        assert f.definition == ACM[f.criterion]


def test_every_finding_states_what_a_human_must_still_do():
    for f in assess(_fake_evidence()):
        assert f.needs_human and len(f.needs_human) > 30



# --------------------------------------------------------------------------
# Iteration 75 - documented counts must be derived, not asserted from memory
#
# "46 tests" in spend.py, "29 regression tests" in AGENTS.md and
# REPRODUCTION.md, "18 tests" twice in README.md - four documents asserting
# four DIFFERENT counts, all of them wrong, while the suite stood at 75. Every
# one was correct when written. None was correct when read.
#
# The same failure mode as the truncated file trees and the never-firing
# RFC1918 pattern: a claim that silently stops being true. So this test scans
# the present-tense documentation and fails if any stated count drifts.
# CHANGELOG.md is deliberately excluded - its entries are historical records of
# what was true at that iteration, and rewriting them would be falsifying a log.
# --------------------------------------------------------------------------
def test_documented_test_counts_match_the_actual_suite():
    import re
    root = Path(__file__).resolve().parents[1]
    actual = sum(1 for ln in (root / "tests" / "test_regressions.py")
                 .read_text().splitlines() if ln.startswith("def test_"))
    assert actual > 0
    pat = re.compile(r"(\d+)\s+(?:regression\s+)?tests\b")
    wrong = []
    for name in ("README.md", "AGENTS.md", "REPRODUCTION.md"):
        f = root / name
        if not f.exists():
            continue
        for i, line in enumerate(f.read_text().splitlines(), 1):
            for m in pat.finditer(line):
                if int(m.group(1)) != actual:
                    wrong.append(f"{name}:{i} claims {m.group(1)}, actual {actual}")
    assert not wrong, "stale test counts: " + "; ".join(wrong)


def test_spend_report_derives_the_test_count():
    """It must be computed, not written down - that is what drifted."""
    from artifact_triage.eval.spend import _n_tests
    root = Path(__file__).resolve().parents[1]
    actual = sum(1 for ln in (root / "tests" / "test_regressions.py")
                 .read_text().splitlines() if ln.startswith("def test_"))
    assert _n_tests() == actual



# --------------------------------------------------------------------------
# Iteration 77 - the reporting path that had never executed
#
# `_report` in falsified_run.py read `b_ment` and `s_ment` as bare names. They
# are locals of a DIFFERENT function; in `_report` they were undefined. The
# floor-free metric was added in iteration 70 and backfilled onto runs that had
# ALREADY been recorded, so this print path was never once exercised. It
# crashed the first time it ran for real - after the API calls were paid for,
# and before any result was written to disk.
#
# The fix is two-part: read from `summary`, and checkpoint each trial before
# anything that can fail touches it. This test covers the first part by doing
# the thing nothing had done: calling the function.
# --------------------------------------------------------------------------
def _fake_summary():
    return {
        "n_artifacts": 15, "baseline_noticed": 0, "solution_noticed": 8,
        "baseline_mentions_absence": 0, "solution_mentions_absence": 15,
        "baseline_eligible": 14, "baseline_downgraded_eligible": 0,
        "baseline_at_floor": ["a"],
        "solution_eligible": 8, "solution_downgraded_eligible": 8,
        "solution_at_floor": ["b"] * 7,
        "verifier_detected": 75, "injected_claims": 75, "usd": 0.1,
    }


def test_falsified_report_runs_without_undefined_names():
    import io
    import contextlib
    from artifact_triage.eval import falsified_run as fr
    d = _fake_summary()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fr._report(d, d["n_artifacts"],
                   d["baseline_downgraded_eligible"], d["baseline_eligible"],
                   d["baseline_at_floor"],
                   d["solution_downgraded_eligible"], d["solution_eligible"],
                   d["solution_at_floor"],
                   d["verifier_detected"], d["injected_claims"], d["usd"])
    out = buf.getvalue()
    assert "MENTIONS THE ABSENCE" in out
    assert "0/15" in out and "15/15" in out


def test_falsified_report_reads_mentions_from_summary_not_scope():
    """Changing the summary must change the printed figure."""
    import io
    import contextlib
    from artifact_triage.eval import falsified_run as fr
    d = _fake_summary()
    d["solution_mentions_absence"] = 3
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fr._report(d, d["n_artifacts"],
                   d["baseline_downgraded_eligible"], d["baseline_eligible"],
                   d["baseline_at_floor"],
                   d["solution_downgraded_eligible"], d["solution_eligible"],
                   d["solution_at_floor"],
                   d["verifier_detected"], d["injected_claims"], d["usd"])
    assert "3/15" in buf.getvalue()


def test_paid_trials_are_checkpointed_before_reporting():
    """A display failure must never destroy data that cost money."""
    import inspect
    from artifact_triage.eval import falsified_run as fr
    src = inspect.getsource(fr.main)
    ck = src.index("_checkpoint(")
    rep = src.index("_report(")
    assert ck < rep, "checkpoint must happen before anything that can fail"
    assert "try:" in src, "reporting must not be able to abort a paid run"



# --------------------------------------------------------------------------
# Iteration 79 - the report must not contradict itself about human review
#
# `Decision.explain()` said "handled automatically - evidence was sufficient",
# and the CLI printed nothing about review when no rule fired. Two sections
# later the same report stated that `Consistent` can never be settled by a
# machine. A report that claims autonomy in one section and disclaims it in
# the next is the identical defect to the earlier "5 missing paths / all paths
# were found" bug - and it is the defect this whole project detects.
# --------------------------------------------------------------------------
def test_no_escalation_does_not_claim_full_automation():
    from artifact_triage.solution.escalate import Decision
    txt = Decision(False, []).explain()
    assert "automatic" not in txt.lower()
    assert "Consistent" in txt


def test_report_always_states_the_reviewers_irreducible_role():
    import inspect
    from artifact_triage import cli
    src = inspect.getsource(cli.render)
    assert "Always required of a reviewer" in src
    i = src.index("Always required of a reviewer")
    j = src.index('if model.get("escalated")', i)
    assert i < j, "the always-required note must not be inside the escalated branch"



# --------------------------------------------------------------------------
# Iteration 80 - the budget guard that no test had ever entered
#
# A coverage sweep (which functions are never entered by the tests or a full
# CLI run?) found `budget_check` among them. The guard protecting a hard $5
# ceiling had never once executed under test.
#
# Reading it revealed the real defect: `budget_check()` is called from
# `client()`, which runs ONCE per run. `ask()` meters every call but re-checks
# nothing. A run starting at $4.95 passed the check and could then make
# hundreds of billed calls with nothing watching - the ceiling was enforced at
# run granularity, not spend granularity, which is no ceiling at all for any
# run large enough to matter.
#
# Same family as the RFC1918 pattern that could not fire and the `_report`
# path that had never executed: code that looks like a safeguard and isn't.
# --------------------------------------------------------------------------
def _isolated_ledger(tmp, entries_usd):
    """Point the ledger at a temp file so tests never touch real spend data."""
    import json
    from artifact_triage.common import ledger
    p = Path(tmp) / "ledger.jsonl"
    p.write_text("".join(json.dumps({"kind": "call", "usd": u, "calls": 1}) + "\n"
                         for u in entries_usd))
    ledger.LEDGER = p
    return p


def test_budget_check_refuses_to_start_past_the_ceiling():
    import tempfile
    from artifact_triage.common import budget, ledger
    old_ledger, old_guard = ledger.LEDGER, budget.GUARD_USD
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _isolated_ledger(tmp, [4.0, 1.5])      # $5.50 spent
            budget.GUARD_USD = 5.0
            budget.reset()
            raised = False
            try:
                budget.check()
            except SystemExit:
                raised = True
            assert raised, "the guard must raise, not warn"
    finally:
        ledger.LEDGER, budget.GUARD_USD = old_ledger, old_guard
        budget.reset()


def test_budget_guard_can_be_disabled_explicitly():
    import tempfile
    from artifact_triage.common import budget, ledger
    old_ledger, old_guard = ledger.LEDGER, budget.GUARD_USD
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _isolated_ledger(tmp, [99.0])
            budget.GUARD_USD = 0.0
            budget.reset()
            budget.check()                          # must not raise
    finally:
        ledger.LEDGER, budget.GUARD_USD = old_ledger, old_guard
        budget.reset()


def test_a_long_run_is_stopped_the_moment_it_crosses_the_ceiling():
    """The defect: the ceiling was checked once, then hundreds of calls ran."""
    import tempfile
    from artifact_triage.common import budget, ledger
    old_ledger, old_guard = ledger.LEDGER, budget.GUARD_USD
    try:
        with tempfile.TemporaryDirectory() as tmp:
            _isolated_ledger(tmp, [4.90])           # just under the ceiling
            budget.GUARD_USD = 5.0
            budget.reset()
            budget.check()                          # start of run: passes

            calls = 0
            stopped = False
            try:
                for _ in range(500):                # bill call by call
                    calls += 1
                    budget.enforce(0.01)
            except SystemExit:
                stopped = True
            assert stopped, "the run was never stopped - the ceiling is not a ceiling"
            assert calls < 500, "stopped only after every call had already run"
    finally:
        ledger.LEDGER, budget.GUARD_USD = old_ledger, old_guard
        budget.reset()


def test_the_ceiling_is_enforced_per_call_not_only_at_client_creation():
    import inspect
    from artifact_triage.common import llm
    assert "enforce" in inspect.getsource(llm._meter), \
        "metering every call is useless if none of them checks the ceiling"


def test_budget_policy_is_not_a_provenance_influencer():
    """Editing budget code must not mark recorded results stale.

    It cannot change a single token of model output, and a staleness detector
    that cries wolf trains you to ignore it.
    """
    from artifact_triage.common.provenance import INFLUENCERS
    for kind, files in INFLUENCERS.items():
        assert not any("budget.py" in f for f in files), \
            f"{kind} lists budget.py, which cannot affect any result"



# --------------------------------------------------------------------------
# Iteration 81 - a serialisation layer for an output mode that did not exist
#
# The coverage sweep found `to_dict` unused on CriterionFinding, DockerReport,
# PinReport and PortabilityReport. Four dataclasses carried serialisers that
# nothing called, because the CLI emitted markdown only.
#
# That was not stray code - it pointed at a product gap. The whole thesis is
# reviewer CAPACITY: a chair triaging a venue's worth of artifacts needs a
# sortable record per repository, not prose read one repo at a time. `--json`
# is the missing mode, and it makes the existing serialisers live.
# --------------------------------------------------------------------------
def test_json_mode_emits_every_check_not_just_the_prose():
    import json as _json
    from artifact_triage.solution.criteria import assess, summary
    from artifact_triage.solution.verify import verify
    fixtures = sorted(Path("data/fixtures").glob("*.json"))
    if not fixtures:
        return
    fx = _json.loads(fixtures[0].read_text())
    ev = verify(fx)
    crit = assess(ev)
    payload = {"verified": ev.to_dict(),
               "acm_functional": [c.to_dict() for c in crit],
               "acm_summary": summary(crit)}
    # must round-trip through JSON - a report a machine cannot read is markdown
    round_tripped = _json.loads(_json.dumps(payload))
    assert len(round_tripped["acm_functional"]) == 4
    for c in round_tripped["acm_functional"]:
        assert {"criterion", "definition", "verdict", "mechanical",
                "evidence", "needs_human"} <= set(c)


def test_criteria_summary_never_claims_consistency_was_settled():
    from artifact_triage.solution.criteria import assess, summary
    clean = summary(assess(_fake_evidence()))
    dirty = summary(assess(_fake_evidence(claims_broken=9,
                                          broken_paths=["x.py"] * 9)))
    for txt in (clean, dirty):
        assert "onsistency" in txt or "onsistent" in txt


def test_cli_exposes_a_machine_readable_mode():
    import inspect
    from artifact_triage import cli
    src = inspect.getsource(cli.main)
    assert '"--json"' in src
    assert "acm_functional" in src



# --------------------------------------------------------------------------
# Iteration 82 - a CI gate, because "at publication time" needs an exit code
#
# Arvan et al. (EMNLP 2022) recommend evaluating artifacts "at the time of
# publication". In practice that means a check in the author's own CI, and CI
# gates on exit codes. The CLI exited 0 whether an artifact was clean or had 15
# missing documented paths, so the moment the literature identifies was not
# reachable. Opt-in via --fail-on-findings, so plain reporting still exits 0.
# --------------------------------------------------------------------------
def test_ci_gate_is_opt_in_and_fails_only_on_concerns():
    from artifact_triage.cli import _exit_code
    from artifact_triage.solution.criteria import assess
    clean = assess(_fake_evidence())
    dirty = assess(_fake_evidence(claims_broken=5, broken_paths=["gone.py"]))
    assert _exit_code(dirty, False) == 0, "default must stay 0 - it is a report"
    assert _exit_code(dirty, True) != 0, "the gate must fail a broken artifact"
    assert _exit_code(clean, True) == 0, "a clean artifact must not fail CI"


def test_not_checkable_alone_never_fails_ci():
    """`Consistent` is un-checkable for EVERY artifact. Failing on it would
    make the gate fire always, which is the same as never."""
    from artifact_triage.cli import _exit_code
    from artifact_triage.solution.criteria import assess
    assert _exit_code(assess(_fake_evidence()), True) == 0


# --------------------------------------------------------------------------
# Iteration 83 - one experiment reported a range, the other a point estimate
# --------------------------------------------------------------------------
def test_comparison_records_a_history_rather_than_overwriting_it():
    import inspect
    from artifact_triage.eval import compare
    src = inspect.getsource(compare)
    assert "HISTORY" in src and 'open("a")' in src, \
        "MAE varies between runs; overwriting it hides the spread"



# --------------------------------------------------------------------------
# Iteration 85 - the scrubber leaked the answer for British spellings
#
# `artefacts?|artifacts?\s*(?:evaluated|available)...` is an UNGROUPED
# alternation: it reads as (artefacts?) OR (artifacts?...). So the British
# spelling matched the bare word ALONE.
#
#     "Artefacts Evaluated - Reusable"  ->  "[REDACTED] Evaluated - Reusable"
#
# The label removed, the tier left in plain sight - the exact failure the
# badge-image comment in that file already warned about. It also over-redacted
# every innocent "artefact".
#
# The separator class was too narrow as well: real READMEs write the tier as
# "(Reusable)", "/ Functional" and "_reusable", none of which matched.
#
# Verified against the corpus: NO stored fixture leaked, and the fix is a
# byte-for-byte no-op on all 15, so no recorded result was ever contaminated.
# This was a latent hole, and it is reported as one.
# --------------------------------------------------------------------------
LEAKS_THE_ANSWER = [
    "Artifacts Evaluated - Reusable",
    "Artefacts Evaluated - Reusable",          # the precedence bug
    "Artefacts Evaluated — Functional",
    "Artifacts Evaluated (Reusable)",          # parenthesised
    "Artifacts Evaluated / Functional",        # slash
    "artifacts_evaluated_reusable",            # underscore, e.g. a badge file
    "Artifact Evaluated: Reusable",
    "This artifact is REUSABLE.",
    "We got the Reusable stamp from the AE committee.",
    "Results Reproduced",
]

MUST_SURVIVE_UNTOUCHED = [
    "Our artefact implements the algorithm.",   # British spelling, no badge
    "This artifact contains our tool.",
    "The code is reusable across projects.",
    "A functional programming approach was used.",
    "See the functional tests in tests/.",
    "Artefact Evaluation is discussed in the paper.",
]


def test_no_phrasing_of_the_badge_survives_scrubbing():
    from artifact_triage.corpus.scrub import scrub
    for text in LEAKS_THE_ANSWER:
        out = scrub(text).text.lower()
        for tier in ("reusable", "functional", "reproduced"):
            assert tier not in out, f"{text!r} leaked {tier!r} as {out!r}"


def test_scrubbing_does_not_destroy_innocent_prose():
    """Over-redaction cannot bias the comparison, but it still costs realism."""
    from artifact_triage.corpus.scrub import scrub
    for text in MUST_SURVIVE_UNTOUCHED:
        assert scrub(text).text == text, f"over-redacted: {text!r}"


def test_bare_artefact_is_not_redacted_by_the_committee_pattern():
    """This bug was REINTRODUCED while fixing it, in the very next pattern."""
    from artifact_triage.corpus.scrub import scrub
    assert scrub("Our artefact is here.").text == "Our artefact is here."
    assert "committee" not in scrub(
        "Artefact Evaluation Committee approved this").text.lower()


def test_the_fix_does_not_change_the_recorded_corpus():
    """If it did, every published result would be stale."""
    import json as _json
    from artifact_triage.corpus.scrub import scrub
    for p in sorted(Path("data/fixtures").glob("*.json")):
        rm = _json.loads(p.read_text()).get("readme") or ""
        assert scrub(rm).text == rm, f"{p.name} would change on re-scrub"


def test_no_tier_word_survives_anywhere_in_the_stored_corpus():
    import json as _json
    import re as _re
    pat = _re.compile(r"\b(functional|reusable)\b", _re.I)
    for p in sorted(Path("data/fixtures").glob("*.json")):
        rm = _json.loads(p.read_text()).get("readme") or ""
        assert not pat.search(rm), f"{p.name} discloses its tier"


# --------------------------------------------------------------------------
# Iteration 86 - the corpus had no fingerprint at all
#
# scrub.py is the strongest single lever on what a model can conclude, and it
# appeared in NO influencer list. But it does not influence a result directly:
# baseline and solution read committed fixtures, so the FIXTURES are the
# interface. Fingerprinting the corpus separately marks scrubbing changes as
# corpus changes, without falsely invalidating results whose inputs are intact.
# --------------------------------------------------------------------------
def test_corpus_fingerprint_covers_the_fixtures_not_just_the_code():
    import tempfile
    from artifact_triage.common import provenance as pv
    before = pv.corpus_fingerprint()
    fixtures = sorted(Path("data/fixtures").glob("*.json"))
    if not fixtures:
        return
    target = fixtures[0]
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n")      # one byte of difference
        assert pv.corpus_fingerprint() != before, \
            "changing a fixture must change the corpus fingerprint"
    finally:
        target.write_bytes(original)
    assert pv.corpus_fingerprint() == before, "fingerprint must be restored"


def test_missing_corpus_fingerprint_is_not_reported_as_stale():
    """Results recorded before the check existed are unknown, not wrong."""
    from artifact_triage.common.provenance import fingerprint, is_stale
    payload = {"_provenance": {"kind": "solution", "commit": "abc",
                               "code_fingerprint": fingerprint("solution")}}
    stale, why = is_stale(payload)
    assert not stale, why
    assert "predates" in why


def test_a_changed_corpus_marks_results_stale():
    from artifact_triage.common.provenance import fingerprint, is_stale
    payload = {"_provenance": {"kind": "solution", "commit": "abc",
                               "code_fingerprint": fingerprint("solution"),
                               "corpus_fingerprint": "deadbeefcafe"}}
    stale, why = is_stale(payload)
    assert stale and "corpus changed" in why



# --------------------------------------------------------------------------
# Iteration 87 - external URLs were counted as broken repo paths
#
# The token pattern cannot contain ":", so
# "https://github.com/other/repo/blob/main/tool.py" degraded to
# "//github.com/.../tool.py" and survived `_is_path` as a claimed repository
# file - one that by construction can never exist here, and was therefore
# counted as a broken claim.
#
# Measured on the 732-artifact sweep: 126 of 1,190 broken paths (10.6%) were
# links to OTHER projects' files - github.com/..., conda.io/docs/...,
# pandoc.org/MANUAL.html. A README linking to another project's source is not
# claiming that source lives in this repository.
#
# The datasheet already warned this could happen. Nobody had measured it, and
# an unquantified caveat next to a headline percentage is not a disclosure.
# --------------------------------------------------------------------------
def test_external_urls_are_not_claimed_repository_paths():
    from artifact_triage.corpus.fetch import referenced_paths
    for text in (
        "See https://example.com/docs/setup.py for details",
        "Based on https://github.com/other/repo/blob/main/tool.py",
        "Docs at www.pandoc.org/MANUAL.html",
        "Installer: https://repo.anaconda.com/archive/Anaconda3-2024.06-1.sh",
        "ftp://mirror.org/pub/data.csv",
    ):
        assert referenced_paths(text) == [], f"{text!r} -> {referenced_paths(text)}"


def test_stripping_urls_does_not_lose_genuine_relative_paths():
    from artifact_triage.corpus.fetch import referenced_paths
    got = referenced_paths(
        "Clone https://github.com/me/mine.git then run setup.py and "
        "scripts/go.sh; see [docs](docs/guide.md)")
    assert set(got) == {"setup.py", "scripts/go.sh", "docs/guide.md"}, got


def test_a_path_inside_a_url_is_not_resurrected_by_the_inline_scan():
    """Backticked URLs must be stripped too, not just prose ones."""
    from artifact_triage.corpus.fetch import referenced_paths
    assert referenced_paths("Run `https://x.org/a/b/run.py` now") == []



# --------------------------------------------------------------------------
# Iteration 88 - the cache stored a conclusion instead of an input
#
# The prevalence cache stored `readme_referenced_paths`, a DERIVED value. When
# the extractor was fixed to stop counting external URLs as repository files,
# re-running the sweep reproduced the old numbers exactly: the fix could not
# reach any cached artifact.
#
# Worse, the provenance stamp on that output said "current". It hashed the NEW
# extractor while the numbers came from values the OLD one produced - a
# staleness detector certifying stale numbers, which is the failure mode this
# project argues is worse than having no detector.
#
# Recomputing must use the RAW README, not the stored one: the stored copy is
# truncated to 20,000 characters and 45 cached entries sit exactly at that cap,
# so re-extracting from it would silently undercount.
# --------------------------------------------------------------------------
def test_cached_profiles_recompute_derived_values():
    import inspect
    from artifact_triage.eval import prevalence
    src = inspect.getsource(prevalence.profile)
    assert "_rederive" in src, \
        "a cached derived value cannot be corrected by fixing the code"


def test_rederivation_reads_the_full_readme_not_the_truncated_copy():
    import inspect
    from artifact_triage.eval import prevalence
    src = inspect.getsource(prevalence._rederive)
    i, j = src.index("readme(slug)"), src.index('fx.get("readme")')
    assert i < j, "the raw README must be preferred over the truncated copy"


def test_no_external_url_survives_as_a_broken_claim_in_prevalence():
    """The published rate must not count other projects' files as missing."""
    import json as _json
    import re as _re
    p = Path("results/prevalence.json")
    if not p.exists():
        return
    dom = _re.compile(
        r"^(?:www\.)?[\w-]+\.(?:com|org|net|io|edu|gov|de|uk|cn|ai|dev|me|co)"
        r"(?:/|$)", _re.I)
    offenders = [pp for r in _json.loads(p.read_text())["per_artifact"]
                 for pp in r.get("broken_paths", []) if dom.match(pp)]
    assert not offenders, f"{len(offenders)} URL(s) counted as broken: {offenders[:5]}"



# --------------------------------------------------------------------------
# Iteration 90 - the anti-cry-wolf mechanism cried wolf
#
# The corpus fingerprint was added so that changes to scrubbing/extraction mark
# the CORPUS stale without falsely invalidating results. It was then applied to
# every result kind - so rebuilding `data/fixtures` marked `prevalence` stale
# for data prevalence never reads. The fix for cry-wolf, itself crying wolf.
#
# The rule that keeps recurring: a fingerprint must cover EXACTLY what a result
# consumed. Too little certifies stale numbers; too much trains you to ignore
# the alarm.
# --------------------------------------------------------------------------
def test_corpus_fingerprint_applies_only_to_fixture_consumers():
    from artifact_triage.common.provenance import (FIXTURE_KINDS, stamp)
    assert "prevalence" not in FIXTURE_KINDS
    assert "corpus_fingerprint" not in stamp("prevalence")
    assert "corpus_fingerprint" in stamp("solution")


def test_a_recorded_corpus_hash_is_ignored_for_non_fixture_kinds():
    """prevalence.json still carries an old hash; it must not go stale on it."""
    from artifact_triage.common.provenance import fingerprint, is_stale
    payload = {"_provenance": {"kind": "prevalence", "commit": "abc",
                               "code_fingerprint": fingerprint("prevalence"),
                               "corpus_fingerprint": "staleaaaaaaa"}}
    stale, why = is_stale(payload)
    assert not stale, why


# --------------------------------------------------------------------------
# Iteration 91 - "verified" numbers that verified nothing
#
# check_claims matches a literal anywhere in the document. Printing WHERE each
# match landed exposed two checks that proved nothing:
#   - trial count matched the bare string "3", on 56 lines
#   - solution MAE matched "0.700" on the anti-calibrated-CONFIDENCE sentence,
#     not the MAE table - a coincidence reported as a pass
# An unaudited green check is exactly what this project argues against.
# --------------------------------------------------------------------------
def test_claim_literals_are_distinctive_enough_to_verify_something():
    import subprocess
    out = subprocess.run([sys.executable, "scripts/check_claims.py"],
                         capture_output=True, text=True,
                         cwd=str(Path(__file__).resolve().parents[1]))
    assert "TOO LOOSE" not in out.stdout, out.stdout[-900:]
    assert "FAIL" not in out.stdout, out.stdout[-900:]



# --------------------------------------------------------------------------
# Iteration 92 - a full stop deleted ten real artifacts from the corpus
#
# The GitHub URL pattern allows "." inside a repository name, so a link written
# in prose - "see https://github.com/owner/repo." - captured the sentence's full
# stop. GitHub does not permit a trailing dot in a repository name, so those
# slugs could only ever 404.
#
# 10 of 769 harvested slugs were affected, and ALL TEN were verified to be real
# repositories via the GitHub API. They were not noise being correctly rejected;
# they were legitimate artifacts silently dropped from the population, which
# quietly biases a prevalence measurement.
#
# Three more were github.com paths that are not repositories at all -
# `user-attachments/assets` comes from pasted image URLs.
# --------------------------------------------------------------------------
def test_sentence_full_stop_is_not_part_of_the_repository_name():
    from artifact_triage.corpus.zenodo import github_repos
    got = github_repos({"metadata": {"d":
        "The code is at https://github.com/cesar-andress/caliper."}})
    assert got == ["cesar-andress/caliper"], got


def test_github_non_repository_paths_are_rejected():
    from artifact_triage.corpus.zenodo import github_repos
    got = github_repos({"metadata": {"d":
        "![x](https://github.com/user-attachments/assets/abc123) "
        "https://github.com/apps/renovate "
        "https://github.com/features/actions "
        "https://github.com/real/project"}})
    assert got == ["real/project"], got


def test_git_suffix_and_trailing_dot_are_both_handled():
    from artifact_triage.corpus.zenodo import github_repos
    got = github_repos({"metadata": {"d":
        "https://github.com/a/b.git and https://github.com/c/d.git."}})
    assert got == ["a/b", "c/d"], got


def test_no_harvested_slug_is_structurally_invalid():
    import json as _json
    p = Path("data/discovered.jsonl")
    if not p.exists():
        return
    bad = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        slug = _json.loads(line)["repo"]
        owner, _, name = slug.partition("/")
        if not name or name.endswith(".") or owner.lower() in (
                "user-attachments", "apps", "features", "assets"):
            bad.append(slug)
    assert not bad, f"invalid slugs harvested: {bad[:8]}"



# --------------------------------------------------------------------------
# Iteration 93 - `make discover` silently shrank the corpus
#
# The corpus reached 769 repositories through a STRATIFIED harvest across
# publication years. A plain `make discover` finds 398 and overwrote the larger
# file with the smaller one - quietly shrinking the measured population by half.
#
# It happened during this work and was caught only because a backup existed. A
# build target that destroys data without saying so is a defect regardless of
# whether anyone has lost anything to it yet.
# --------------------------------------------------------------------------
def test_discovery_refuses_to_replace_a_larger_corpus():
    import inspect
    from artifact_triage.corpus import discover
    src = inspect.getsource(discover)
    assert "REFUSING to shrink the corpus" in src
    i = src.index("REFUSING to shrink the corpus")
    assert "--force" in src[max(0, i - 400):i + 400], \
        "there must be an explicit way to override, or the guard is a wall"


def test_slug_migration_is_idempotent():
    """Re-running the correction on a corrected corpus must change nothing."""
    import json as _json
    p = Path("data/discovered.jsonl")
    if not p.exists():
        return
    from artifact_triage.corpus.zenodo import _NOT_REPOS
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        owner, _, name = _json.loads(line)["repo"].partition("/")
        assert name and not name.endswith(".")
        assert owner.lower() not in _NOT_REPOS



# --------------------------------------------------------------------------
# Iteration 94 - the repro guide quoted a clone size that had grown
#
# REPRODUCTION.md promised a "37 MB" shallow clone. A clean-room clone measured
# 46 MB: cache files were added over time and the documented figure was never
# revisited. Small, but it is a documented claim about the artifact that had
# drifted from the artifact - the exact defect this project detects in other
# people's READMEs, in this project's own reproduction guide.
#
# Checked against the tracked tree rather than a remembered number.
# --------------------------------------------------------------------------
def test_documented_clone_size_matches_the_tracked_tree():
    import re
    import subprocess
    root = Path(__file__).resolve().parents[1]
    doc = (root / "REPRODUCTION.md").read_text()
    m = re.search(r"shallow clone \*\*(\d+) MB", doc)
    assert m, "REPRODUCTION.md no longer states a clone size"
    claimed = int(m.group(1))
    try:
        files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                               text=True, timeout=60).stdout.split()
    except Exception:
        return                      # not a git checkout; nothing to compare
    if not files:
        return
    total = 0
    for f in files:
        p = root / f
        if p.exists():
            total += p.stat().st_size
    mb = total / 1e6
    # Tracked bytes plus git object overhead. Allow generous slack, and fail
    # only when the claim is off by enough to mislead someone sizing a disk.
    assert abs(mb - claimed) <= 15, (
        f"REPRODUCTION.md claims {claimed} MB; tracked files total {mb:.0f} MB")



# --------------------------------------------------------------------------
# Iteration 95 - a post-condition whose docstring claimed it was wired in
#
# `assert_clean`'s docstring read "Used as a post-condition in the corpus
# build." It was not: the only caller was the trajectory exporter. The corpus
# build - the one place badge leakage would actually contaminate a result - had
# no check at all, while the code asserted it did. A documented guarantee the
# repository does not contain is precisely the defect this project detects in
# other people's READMEs.
#
# Wiring it in was not enough. I first wrote that this check "is exactly how
# the British-spelling leak survived", then TESTED that claim and it was false:
# "[REDACTED] Evaluated - Reusable" matches no pattern, so a second scrubbing
# pass sees nothing. The comment was corrected rather than left flattering.
#
# So a second post-condition catches that bug's actual signature - the label
# redacted, the tier orphaned beside the hole - which is detectable by SHAPE
# even when the phrasing matches nothing.
# --------------------------------------------------------------------------
def test_corpus_build_actually_runs_the_leakage_post_condition():
    import inspect
    from artifact_triage.corpus import fetch
    assert "assert_clean" in inspect.getsource(fetch.build), \
        "the corpus build must run the check its docstring promised"


def test_orphaned_tier_beside_a_redaction_is_caught():
    from artifact_triage.corpus.scrub import assert_clean
    for leak in ("[REDACTED] Evaluated - Reusable",
                 "[REDACTED] (Reusable)",
                 "[REDACTED]/Functional",
                 "[REDACTED]_reusable"):
        try:
            assert_clean(leak)
        except AssertionError:
            continue
        raise AssertionError(f"orphaned tier not caught: {leak!r}")


def test_orphan_check_does_not_fire_on_ordinary_prose():
    """A false positive here breaks the corpus build, so it must be narrow."""
    from artifact_triage.corpus.scrub import assert_clean
    for ok in ("[REDACTED] and the code is reusable in other projects",
               "[REDACTED]\n\nThe functional tests live in tests/",
               "A functional programming approach was used.",
               "[REDACTED] available at the DOI above"):
        assert_clean(ok)


def test_every_stored_fixture_passes_the_post_condition():
    import json as _json
    from artifact_triage.corpus.scrub import assert_clean
    for p in sorted(Path("data/fixtures").glob("*.json")):
        assert_clean(_json.loads(p.read_text()).get("readme") or "")



# --------------------------------------------------------------------------
# Iteration 96 - the datasheet promised byte-identical re-runs, and was wrong
#
# "All measurement code is deterministic. Re-running it on the same commits
# produces byte-identical output." Two consecutive runs disagreed - on exactly
# one field. `stale_days` is an AGE, computed against `datetime.now()` at each
# call, so every row was timed against a slightly later clock and the
# determinism claim was false.
#
# Small, but it is the headline promise of the reproducibility section, and it
# is the same defect the dataset exists to measure.
# --------------------------------------------------------------------------
def test_age_is_measured_against_a_recorded_reference_not_now():
    from datetime import datetime, timezone
    from artifact_triage.eval import prevalence
    ref = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = prevalence.age_days("2025-12-25T00:00:00Z", ref=ref)
    b = prevalence.age_days("2025-12-25T00:00:00Z", ref=ref)
    assert a == b == 7.0, (a, b)


def test_prevalence_records_the_reference_clock():
    import json as _json
    p = Path("results/prevalence.json")
    if not p.exists():
        return
    assert _json.loads(p.read_text()).get("measured_at"), \
        "an age is meaningless without the clock it was measured against"


def test_datasheet_does_not_overclaim_byte_identical_reruns():
    for p in (Path("dataset/DATASHEET.md"),
              Path("src/artifact_triage/eval/export_dataset.py")):
        if not p.exists():
            continue
        t = p.read_text()
        if "byte-identical" in t:
            assert "stale_days" in t, (
                f"{p} promises byte-identical output without naming the one "
                f"field that cannot be")



# --------------------------------------------------------------------------
# Iteration 97 - the commit field in a provenance stamp could lie
#
# `stamp()` recorded `git rev-parse HEAD` with no check for uncommitted
# changes. Results produced from a modified tree were labelled with a commit
# whose code never produced them - a hash that looks authoritative and cannot
# recover what actually ran.
#
# It bit here: results stamped `7363401` were produced by code that landed two
# commits later, so diffing against that commit gave a misleading answer until
# the discrepancy was spotted by hand.
# --------------------------------------------------------------------------
def test_commit_stamp_marks_a_dirty_working_tree():
    import inspect
    from artifact_triage.common import provenance
    src = inspect.getsource(provenance.commit)
    assert "status" in src and "-dirty" in src, \
        "a stamp from a modified tree must not look like a clean commit"


def test_staleness_reports_which_functions_changed():
    """'Stale' with no detail invites a needless paid re-run, or a shrug."""
    from artifact_triage.common.provenance import changed_functions
    out = changed_functions("falsified", "HEAD")
    assert isinstance(out, list)
    for entry in out:
        assert ":" in entry, entry


def test_changed_functions_is_safe_on_a_bad_reference():
    from artifact_triage.common.provenance import changed_functions
    assert changed_functions("falsified", "not-a-real-commit-ref") == []



if __name__ == "__main__":
    import traceback
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc(limit=2)
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
