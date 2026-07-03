"""PromptRegistry: per-section versions, archive, best-snapshot, stagnation.

Pure state machine — no LLM calls — so it is fully unit-testable. Persisted
atomically to registry.json after every mutation; the whole history (including
rejected candidates) is kept for the paper's per-section trajectory analysis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from fdpo.utils.io import atomic_write_json, read_json

SCHEMA_VERSION = 1


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
    stagnant_rounds: int = 0
    best_version: int = 0
    best_acc: float = -1.0
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
        self._save()

    # ---- reads -------------------------------------------------------------

    def active_prompt(self) -> dict[str, str]:
        return {name: self.sections[name].active_text for name in self.schema}

    def prompt_with(self, section: str, candidate_text: str) -> dict[str, str]:
        """Active prompt with one section swapped for a candidate (gate eval)."""
        prompt = self.active_prompt()
        prompt[section] = candidate_text
        return prompt

    # ---- mutations ---------------------------------------------------------

    def commit(self, section: str, text: str, round_num: int,
               gate: GateResult) -> int:
        """Gate passed: archive the old active version, activate the new one."""
        state = self.sections[section]
        state.versions[state.active_version].status = "archived"
        new_version = Version(len(state.versions), text, round_num,
                              "active", asdict(gate))
        state.versions.append(new_version)
        state.active_version = new_version.version
        self._save()
        return new_version.version

    def reject(self, section: str, text: str, round_num: int,
               gate: GateResult) -> None:
        """Gate failed: record the candidate as rejected; active is unchanged."""
        state = self.sections[section]
        state.versions.append(Version(len(state.versions), text, round_num,
                                      "rejected", asdict(gate)))
        self._save()

    def record_round_acc(self, section: str, acc: float,
                         improve_eps: float = 1e-9) -> None:
        """Track best snapshot and stagnation for a section after a gate eval."""
        state = self.sections[section]
        if acc > state.best_acc + improve_eps:
            state.best_acc = acc
            state.best_version = state.active_version
            state.stagnant_rounds = 0
        else:
            state.stagnant_rounds += 1
        self._save()

    def restore_best_snapshot(self, section: str) -> int:
        state = self.sections[section]
        if state.active_version != state.best_version:
            state.versions[state.active_version].status = "archived"
            state.versions[state.best_version].status = "active"
            state.active_version = state.best_version
        state.stagnant_rounds = 0
        self._save()
        return state.active_version

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
            "sections": {
                name: {
                    "name": s.name,
                    "active_version": s.active_version,
                    "stagnant_rounds": s.stagnant_rounds,
                    "best_version": s.best_version,
                    "best_acc": s.best_acc,
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
        reg.sections = {}
        for name in schema:
            raw = data["sections"][name]
            state = SectionState(
                name=name,
                active_version=raw["active_version"],
                stagnant_rounds=raw["stagnant_rounds"],
                best_version=raw["best_version"],
                best_acc=raw["best_acc"],
                versions=[Version(**v) for v in raw["versions"]],
            )
            reg.sections[name] = state
        return reg
