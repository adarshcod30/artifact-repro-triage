"""Map mechanical findings onto the ACM badge criteria a reviewer must rule on.

WHY THIS EXISTS
---------------
The literature says the bottleneck is reviewer capacity, not policy: across ~750
papers, Artifact Evaluation Committees produced no significant change in artifact
availability, though artifacts that pass AE do work at a higher rate (Olszewski
et al., CCS 2023). Arvan et al. (EMNLP 2022) recommend evaluating artifacts "at
the time of publication".

So the useful output is not a list of findings. It is **the reviewer's own
decision, pre-filled with the parts a machine can settle, and explicit about the
parts it cannot.**

ACM defines `Artifacts Evaluated - Functional` as four named qualities, quoted
verbatim below. Each finding this project produces is evidence for or against a
specific one of them - not a generic quality score.

THE HONEST PART
---------------
One of the four, `Consistent`, is *definitionally* outside mechanical reach: it
asks whether the artifacts relate to the paper's claims, which requires reading
the paper. It is therefore always escalated - not because a confidence threshold
fired, but because no amount of file checking can answer it. Saying so is what
makes the other three trustworthy.

Criteria text quoted from the ACM Artifact Review and Badging policy as
reproduced on conference artifact-evaluation pages.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

# Verbatim ACM definitions. Quoted rather than paraphrased so a reviewer can
# check our reading against the policy they are actually applying.
ACM = {
    "Documented": (
        "At a minimum, an inventory of artifacts is included, and sufficient "
        "description is provided to enable the artifacts to be exercised."),
    "Consistent": (
        "The artifacts are relevant to the associated paper and contribute in "
        "some inherent way to generating its main results."),
    "Complete": (
        "To the extent possible, all components relevant to the paper in "
        "question are included."),
    "Exercisable": (
        "Included scripts and / or software used to generate the results in "
        "the associated paper can be successfully executed."),
}


@dataclass
class CriterionFinding:
    criterion: str
    definition: str
    verdict: str          # supported | concerns | not-checkable
    mechanical: bool      # can a machine settle this at all?
    evidence: list[str]
    needs_human: str      # what a reviewer must still do
    # True when the concern is "we found nothing to check", not "we checked and
    # it is missing". Absence of evidence is a limit of THIS INSTRUMENT; evidence
    # of absence is a defect in the artifact. Conflating them made the CI gate
    # fail 133 of 742 real repositories (17.9%) that have no broken path at all,
    # purely for having a prose README. From a tool that advertises zero false
    # positives, that is the worst possible first impression.
    from_absence: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def assess(ev, pins=None, docker=None, port=None, links=None) -> list[CriterionFinding]:
    """Produce one finding per ACM Functional quality."""
    out: list[CriterionFinding] = []

    # ---- Documented -------------------------------------------------------
    doc_ev, doc_bad = [], []
    if not ev.readme_bytes:
        doc_bad.append("no README found - there is no inventory or description")
    else:
        doc_ev.append(f"README present, {ev.readme_bytes} bytes")
        if ev.claims_total == 0:
            doc_bad.append(
                "the README references no concrete files or directories, so it "
                "provides no checkable description of how to exercise the artifact")
        else:
            doc_ev.append(f"{ev.claims_total} concrete file/directory references")
    # A README with no extractable references is not a broken artifact; it is
    # one this tool cannot speak to. Say so, and do not fail anyone's build for
    # it.
    doc_absence = bool(ev.readme_bytes) and ev.claims_total == 0
    out.append(CriterionFinding(
        "Documented", ACM["Documented"],
        "concerns" if doc_bad else "supported", True,
        doc_ev + doc_bad,
        "Read the README and judge whether the description is *sufficient* to "
        "exercise the artifact. Presence of instructions is checkable; their "
        "adequacy is not.",
        from_absence=doc_absence))

    # ---- Consistent -------------------------------------------------------
    # Deliberately not attempted. Answering it requires reading the paper.
    out.append(CriterionFinding(
        "Consistent", ACM["Consistent"], "not-checkable", False,
        ["Requires comparing the artifact against the paper's claims. No file-"
         "level check can establish that an artifact generates a paper's "
         "results."],
        "Read the paper's claims and confirm the artifact plausibly produces "
        "them. This criterion is always yours."))

    # ---- Complete ---------------------------------------------------------
    # This is the criterion our core check speaks to directly.
    comp_ev, comp_bad = [], []
    if ev.claims_total:
        if ev.claims_broken:
            comp_bad.append(
                f"{ev.claims_broken} of {ev.claims_total} documented paths are "
                f"absent from the repository")
            comp_bad += [f"missing: {p}" for p in ev.broken_paths[:8]]
        else:
            comp_ev.append(f"all {ev.claims_total} documented paths resolve")
    if links and links.get("urls_dead"):
        comp_bad.append(f"{links['urls_dead']} referenced URL(s) are unreachable")
    if pins is not None and pins.manifest is None:
        comp_bad.append("no dependency manifest - the environment is not "
                        "included in any recreatable form")
    # "supported" is a POSITIVE claim: we checked and found nothing wrong. With
    # no README there is nothing to check, and this used to report
    # "Complete - no mechanical concerns" for an artifact that documents
    # nothing at all. That is the same absence/evidence confusion as the CI
    # gate, in the opposite direction: there, absence wrongly failed a build;
    # here it wrongly passes one.
    comp_verdict = ("concerns" if comp_bad
                    else "supported" if comp_ev else "not-checkable")
    if comp_verdict == "not-checkable":
        comp_ev.append("nothing to check - the README documents no file "
                       "references, so completeness was not assessed")
    out.append(CriterionFinding(
        "Complete", ACM["Complete"],
        comp_verdict, True,
        comp_ev + comp_bad,
        "A documented file that does not exist is direct evidence against "
        "completeness. Judge whether the missing components are relevant to the "
        "paper - the check establishes absence, not importance."))

    # ---- Exercisable ------------------------------------------------------
    # We can establish a NECESSARY condition (the scripts exist, the environment
    # is pinned) but never the sufficient one (they run and produce the results).
    ex_ev, ex_bad = [], []
    if ev.has_build_script:
        ex_ev.append("build or install script present")
    if pins is not None and pins.floating:
        ex_bad.append(f"{pins.floating} unpinned dependenc"
                      f"{'y' if pins.floating == 1 else 'ies'} - the environment "
                      f"will resolve differently over time")
    if docker is not None and docker.unpinned:
        ex_bad.append(f"container base image unpinned "
                      f"({', '.join(docker.unpinned[:2])})")
    if port is not None and port.n:
        ex_bad.append(f"{port.n} hard-coded machine-specific value(s) that "
                      f"resolve only on the author's machine")
        ex_bad += [f"{f.file}:{f.line}" for f in port.findings[:4]]
    if ev.broken_paths:
        ex_bad.append("scripts the README instructs you to run are among the "
                      "missing paths above")
    ex_verdict = ("concerns" if ex_bad
                  else "supported" if ex_ev else "not-checkable")
    if ex_verdict == "not-checkable":
        ex_ev.append("nothing to check - no build script, no dependency "
                     "manifest and no container were assessed")
    out.append(CriterionFinding(
        "Exercisable", ACM["Exercisable"],
        ex_verdict, True,
        ex_ev + ex_bad,
        "**Run it.** Everything above is a necessary condition, never a "
        "sufficient one - no static check can show that a script executes and "
        "produces the paper's results."))

    return out


def summary(findings: list[CriterionFinding]) -> str:
    concerns = [f for f in findings if f.verdict == "concerns"]
    if not concerns:
        return ("No mechanical evidence against any checkable Functional "
                "criterion. Consistency and execution still require a reviewer.")
    names = ", ".join(f.criterion for f in concerns)
    return (f"Mechanical evidence raises concerns against: {names}. "
            f"Consistency is never machine-checkable and remains yours.")
