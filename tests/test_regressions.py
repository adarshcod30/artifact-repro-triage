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
