import json
import sys
from pathlib import Path

from classify_document import (
    classify_document,
    is_evidence_grounded,
    requires_classification_review,
)


DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "golden_dataset.json"
)


def load_case(case_id: str) -> dict:
    """Load one case from the golden dataset."""

    with DATASET_PATH.open(encoding="utf-8") as file:
        cases = json.load(file)

    for case in cases:
        if case["id"] == case_id:
            return case

    raise ValueError(f"Case not found: {case_id}")


def inspect_case(case_id: str) -> None:
    """Display the full result for one evaluation case."""

    case = load_case(case_id)

    result = classify_document(
        case["document_text"]
    )

    evidence_grounded = is_evidence_grounded(
        result,
        case["document_text"],
    )

    needs_review = requires_classification_review(
        result,
        case["document_text"],
    )

    print("Case")
    print(f"ID: {case['id']}")
    print(f"Description: {case['description']}")

    print("\nSource document")
    print(case["document_text"])

    print("\nExpected classification")
    print(case["expected_document_type"])

    print("\nObserved result")
    print(result.model_dump_json(indent=2))

    print("\nEvidence grounded")
    print(evidence_grounded)

    print("\nNeeds classification review")
    print(needs_review)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python src\\inspect_case.py CASE_ID"
        )

    inspect_case(sys.argv[1])