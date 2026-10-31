"""scripts/traceability.py: requirement IDs to tests and demo steps (PRD NFR-MAINT-001)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("traceability", ROOT / "scripts" / "traceability.py")
assert spec and spec.loader
trace = importlib.util.module_from_spec(spec)
sys.modules["traceability"] = trace
spec.loader.exec_module(trace)

# "ZZZ" is not an area of the PRD, so these fixtures never count as coverage of a real requirement.


def test_only_must_requirements_are_listed() -> None:
    text = "- **FR-ZZZ-001 [M]** a\n- **FR-ZZZ-002 [S]** b\n- **NFR-ZZZ-003 [M]** c\n"
    assert trace.must_requirements(text) == ["FR-ZZZ-001", "NFR-ZZZ-003"]


def test_references_expand_ranges_and_lists_and_read_test_names() -> None:
    found = trace.references("FR-ZZZ-001..003, FR-ZZZ-007/009 and test_NFR_ZZZ_012_works")
    assert found == {
        "FR-ZZZ-001", "FR-ZZZ-002", "FR-ZZZ-003", "FR-ZZZ-007", "FR-ZZZ-009", "NFR-ZZZ-012",
    }  # fmt: skip


def test_a_name_that_only_contains_the_letters_is_not_a_reference() -> None:
    assert trace.references("AFR-ZZZ-001 and prefix_FR_ZZZ") == set()


def test_every_must_requirement_of_the_prd_is_found() -> None:
    requirements = trace.must_requirements(trace.PRD.read_text())
    assert len(requirements) >= 50
    assert "FR-VIS-020" in requirements
