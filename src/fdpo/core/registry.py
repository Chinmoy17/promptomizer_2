"""PromptRegistry: per-section version history + whole-run bundle commit/reject.

Pure state machine — no LLM calls — so it is fully unit-testable. Persisted
atomically to registry.json after every mutation; the whole history (including
rejected candidates) is kept for the paper's per-section trajectory analysis.

v2 mechanism (see Docs/fdpo_mechanism.md): a round edits zero or more sections
at once via a single optimizer call, gated as ONE whole-prompt candidate.
Stagnation and best-snapshot tracking are therefore whole-run concepts, not
per-section: a bundle either commits (every edited section's new version
activates together) or rejects (every edited section's candidate is recorded
but none activate) atomically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from fdpo.utils.io import atomic_write_json, read_json

SCHEMA_VERSION = 2


@dataclass
class GateResult:
    acc_old: float
    acc_new: float
    rho: float
    passed: bool
    batch_size: int
    n_failures: int          # failures that triggered this rewrite
    recovered_failures: int  # of those, how many the new prompt fixes
    broke: int               # previously-correct gate examples the new prompt breaks


@dataclass
class Version:
    version: int
    text: str
    created_round: int
    status: str              # "active" | "archived" | "rejected"
    gate: dict | None = None


@dataclass
class SectionState:
    name: str
    active_version: int = 0
    versions: list[Version] = field(default_factory=list)

    @property
    def active_text(self) -> str:
        return self.versions[self.active_version].text


class PromptRegistry:
    def __init__(self, schema: tuple[str, ...], seed_sections: dict[str, str],
                 path: Path | None = None):
        self.schema = tuple(schema)
        self.path = Path(path) if path else None
        self.sections: dict[str, SectionState] = {}
        for name in self.schema:
            state = SectionState(name=name)
            state.versions.append(Version(0, seed_sections[name], 0, "active"))
            self.sections[name] = state
        # whole-run stagnation / best-snapshot (v2): starts pointing at the
        # seed (version 0) for every section.
        self.run_stagnant_rounds = 0
        self.run_best_acc = -1.0
        self.run_best_versions: dict[str, int] = {name: 0 for name in self.schema}
        self._save()

    # ---- reads -------------------------------------------------------------

    def active_prompt(self) -> dict[str, str]:
        return {name: self.sections[name].active_text for name in self.schema}

    def best_prompt(self) -> dict[str, str]:
        """The whole-run best-known full prompt (may differ from active_prompt
        if rounds have been attempted since the last commit)."""
        return {name: self.sections[name].versions[v].text
                for name, v in self.run_best_versions.items()}

    def prompt_with_edits(self, edits: dict[str, str]) -> dict[str, str]:
        """Active prompt with a bundle of sections swapped for candidates
        (gate eval) -- edits maps section name -> full new text for that section."""
        prompt = self.active_prompt()
        prompt.update(edits)
        return prompt

    # ---- mutations: whole-prompt bundles ------------------------------------

    def commit_bundle(self, edits: dict[str, str], round_num: int,
                      gate: GateResult) -> dict[str, int]:
        """Gate passed: every edited section's new version activates together.

        Returns {section: new_version_number} for the edited sections.
        """
        new_versions: dict[str, int] = {}
        for section, text in edits.items():
            state = self.sections[section]
            state.versions[state.active_version].status = "archived"
            new_version = Version(len(state.versions), text, round_num,
                                  "active", asdict(gate))
            state.versions.append(new_version)
            state.active_version = new_version.version
            new_versions[section] = new_version.version
        self._save()
        return new_versions

    def reject_bundle(self, edits: dict[str, str], round_num: int,
                      gate: GateResult) -> None:
        """Gate failed: record every edited section's candidate as rejected;
        no section's active version changes."""
        for section, text in edits.items():
            state = self.sections[section]
            state.versions.append(Version(len(state.versions), text, round_num,
                                          "rejected", asdict(gate)))
        self._save()

    # ---- mutations: whole-run stagnation / best-snapshot --------------------

    def record_round(self, passed: bool, acc: float) -> None:
        """v2 stagnation fix: ANY gate pass resets stagnation and updates the
        best-known snapshot to the just-committed state -- a tie ("held
        steady, zero regressions") counts as progress, not stagnation. Only a
        REJECTED round (or a round where nothing was attempted) increments
        the stagnant-round counter.
        """
        if passed:
            self.run_stagnant_rounds = 0
            self.run_best_acc = acc
            self.run_best_versions = {name: s.active_version
                                      for name, s in self.sections.items()}
        else:
            self.run_stagnant_rounds += 1
        self._save()

    def restore_best_snapshot(self) -> dict[str, str]:
        """Roll every section back to the whole-run best-known snapshot."""
        for name, best_version in self.run_best_versions.items():
            state = self.sections[name]
            if state.active_version != best_version:
                state.versions[state.active_version].status = "archived"
                state.versions[best_version].status = "active"
                state.active_version = best_version
        self.run_stagnant_rounds = 0
        self._save()
        return self.active_prompt()

    # ---- stats -------------------------------------------------------------

    def counts(self) -> dict:
        commits = rejects = 0
        for state in self.sections.values():
            for v in state.versions[1:]:
                if v.status == "rejected":
                    rejects += 1
                else:
                    commits += 1
        return {"commits": commits, "rejects": rejects}

    # ---- persistence -------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "schema": list(self.schema),
            "run_stagnant_rounds": self.run_stagnant_rounds,
            "run_best_acc": self.run_best_acc,
            "run_best_versions": self.run_best_versions,
            "sections": {
                name: {
                    "name": s.name,
                    "active_version": s.active_version,
                    "versions": [asdict(v) for v in s.versions],
                }
                for name, s in self.sections.items()
            },
        }

    def _save(self) -> None:
        if self.path is not None:
            atomic_write_json(self.path, self.to_dict())

    @classmethod
    def load(cls, path: Path) -> "PromptRegistry":
        data = read_json(path)
        schema = tuple(data["schema"])
        reg = cls.__new__(cls)
        reg.schema = schema
        reg.path = Path(path)
        reg.run_stagnant_rounds = data.get("run_stagnant_rounds", 0)
        reg.run_best_acc = data.get("run_best_acc", -1.0)
        reg.run_best_versions = data.get("run_best_versions",
                                         {name: 0 for name in schema})
        reg.sections = {}
        for name in schema:
            raw = data["sections"][name]
            state = SectionState(
                name=name,
                active_version=raw["active_version"],
                versions=[Version(**v) for v in raw["versions"]],
            )
            reg.sections[name] = state
        return reg
