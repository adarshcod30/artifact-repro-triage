"""Assemble every deterministic finding into one evidence block for the model.

The solution agent was only ever shown *path* verification, even after four more
checks were built - pinning, container base images, portability and link rot. The
model was reasoning with a fifth of the evidence the system had already gathered,
for free, and none of it hallucinable.

This assembles all of it into a single block. Two rules govern the format:

  FACTS, NOT VERDICTS. The block reports what was found, never what it implies.
  "3 of 12 referenced paths do not exist" is a fact; "documentation is poor" is
  a judgement, and judgement is what the model is there for. Pre-judging in the
  prompt would make the model's answer a restatement of ours.

  ABSENCE IS STATED, NOT OMITTED. A check that found nothing says so. Silence
  is ambiguous between "clean" and "not checked", and a reviewer who cannot tell
  those apart cannot use the report.

Every line is derived from `results` the checks produced. Nothing is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Bundle:
    """Everything deterministic that is known about one artifact."""
    paths: object                       # verify.Evidence
    pins: object | None = None          # pinning.PinReport
    docker: object | None = None        # pinning.DockerReport
    portability: object | None = None   # portability.PortabilityReport
    links: dict | None = None           # links.for_artifact summary

    def as_prompt_block(self) -> str:
        L: list[str] = [
            "VERIFIED FACTS. Each line was established by running code against "
            "the repository, not by reading its documentation. Where these "
            "contradict the README, they are what actually holds.",
            "",
        ]

        ev = self.paths
        L.append("== Documentation consistency ==")
        L.append(f"Files in repository: {ev.n_files}")
        L.append(f"README size: {ev.readme_bytes} bytes")
        if ev.claims_total == 0:
            L.append("The README references no checkable file paths, so no "
                     "documented instruction could be verified either way.")
        else:
            L.append(f"README references {ev.claims_total} file path(s); "
                     f"{ev.claims_broken} do NOT exist in the repository.")
            for p in ev.broken_paths[:12]:
                hint = (ev.suggestions or {}).get(p)
                if hint:
                    L.append(f"  - MISSING: {p}   (closest real file: {hint[0]})")
                else:
                    L.append(f"  - MISSING: {p}   (nothing similar exists)")
            if not ev.broken_paths:
                L.append("  All referenced paths were found.")
        if getattr(ev, "ignored", 0):
            L.append(f"({ev.ignored} author-declared exception(s) applied.)")

        L.append("")
        L.append("== Environment reproducibility ==")
        if self.pins is None:
            L.append("Dependency pinning: not checked.")
        else:
            L.append(f"Dependencies: {self.pins.summary()}")
            for d in self.pins.floating_examples[:6]:
                L.append(f"  - unpinned: {d}")
        if self.docker is None:
            L.append("Container: not checked.")
        elif self.docker.dockerfile is None:
            L.append("Container: no Dockerfile present.")
        else:
            L.append(f"Container: {self.docker.summary()}")

        L.append(f"CI configuration present: {ev.has_ci}")
        L.append(f"Tests present: {ev.has_tests}")
        L.append(f"Licence present: {ev.has_licence}")

        L.append("")
        L.append("== Portability ==")
        if self.portability is None:
            L.append("Not checked.")
        elif self.portability.n == 0:
            L.append(f"No machine-specific values found across "
                     f"{self.portability.files_scanned} inspected file(s).")
        else:
            L.append(f"{self.portability.n} hard-coded value(s) that resolve "
                     f"only on the author's machine:")
            for f in self.portability.findings[:6]:
                L.append(f"  - {f.file}:{f.line}  {f.excerpt[:80]}")

        L.append("")
        L.append("== External links ==")
        if self.links is None:
            L.append("Not checked.")
        else:
            L.append(f"{self.links['urls_checked']} URL(s) checked, "
                     f"{self.links['urls_dead']} dead "
                     f"({self.links['urls_unverifiable']} unverifiable).")
            for u in self.links.get("dead_urls", [])[:5]:
                L.append(f"  - DEAD: {u}")

        return "\n".join(L)


def gather(fixture: dict, *, slug: str | None = None, with_network: bool = False,
           ignores: list[str] | None = None) -> Bundle:
    """Run every deterministic check that the available inputs allow.

    `with_network=False` keeps this offline and reproducible from fixtures,
    which is how the evaluation runs. The network-dependent checks (file
    contents, live URLs) are opt-in so a reported number never silently depends
    on what the internet looked like that afternoon.
    """
    from artifact_triage.solution.verify import verify

    slug = slug or fixture["artifact_id"]
    bundle = Bundle(paths=verify(fixture, ignores=ignores))

    if not with_network:
        return bundle

    from artifact_triage.solution.links import for_artifact
    from artifact_triage.solution.pinning import analyse, analyse_docker
    from artifact_triage.solution.portability import inspect

    tree = fixture["file_tree"]
    bundle.pins = analyse(slug, tree)
    bundle.docker = analyse_docker(slug, tree)
    bundle.portability = inspect(slug, tree)
    bundle.links = for_artifact(slug, fixture.get("readme", ""))
    return bundle


if __name__ == "__main__":
    import json
    from pathlib import Path

    p = sorted(Path("data/fixtures").glob("*.json"))[0]
    fx = json.loads(p.read_text())
    print(gather(fx, with_network=True).as_prompt_block())
