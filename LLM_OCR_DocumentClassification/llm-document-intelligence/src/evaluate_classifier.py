import json
from pathlib import Path
from time import perf_counter

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


def load_golden_dataset() -> list[dict]:
    """Load the human-approved classification cases."""

    with DATASET_PATH.open(encoding="utf-8") as file:
        return json.load(file)


def evaluate() -> None:
    cases = load_golden_dataset()

    classification_correct_count = 0
    grounded_evidence_count = 0
    review_decision_correct_count = 0
    total_duration = 0.0

    print(
        f"{'ID':<6}"
        f"{'Expected':<22}"
        f"{'Actual':<22}"
        f"{'Class':<8}"
        f"{'Evidence':<10}"
        f"{'Review':<8}"
        f"{'Conf.':<8}"
        f"{'Seconds':<8}"
    )
    print("-" * 92)

    for case in cases:
        start_time = perf_counter()

        try:
            result = classify_document(
                case["document_text"]
            )

            duration = perf_counter() - start_time
            total_duration += duration

            classification_correct = (
                result.document_type
                == case["expected_document_type"]
            )

            evidence_grounded = is_evidence_grounded(
                result,
                case["document_text"],
            )

            actual_needs_review = (
                requires_classification_review(
                    result,
                    case["document_text"],
                )
            )

            review_decision_correct = (
                actual_needs_review
                == case[
                    "expected_needs_classification_review"
                ]
            )

            classification_correct_count += int(
                classification_correct
            )
            grounded_evidence_count += int(
                evidence_grounded
            )
            review_decision_correct_count += int(
                review_decision_correct
            )

            print(
                f"{case['id']:<6}"
                f"{case['expected_document_type']:<22}"
                f"{result.document_type:<22}"
                f"{str(classification_correct):<8}"
                f"{str(evidence_grounded):<10}"
                f"{str(review_decision_correct):<8}"
                f"{result.confidence:<8.2f}"
                f"{duration:<8.2f}"
            )

        except Exception as error:
            duration = perf_counter() - start_time
            total_duration += duration

            print(
                f"{case['id']:<6}"
                f"{case['expected_document_type']:<22}"
                f"{'ERROR':<22}"
                f"{'False':<8}"
                f"{'False':<10}"
                f"{'False':<8}"
                f"{0.0:<8.2f}"
                f"{duration:<8.2f}"
            )

            print(f"  Error: {error}")

    total_cases = len(cases)

    classification_accuracy = (
        classification_correct_count / total_cases
    )

    evidence_grounding_rate = (
        grounded_evidence_count / total_cases
    )

    review_routing_accuracy = (
        review_decision_correct_count / total_cases
    )

    average_duration = total_duration / total_cases

    print("\nClassification evaluation summary")
    print(f"Cases: {total_cases}")

    print(
        "Classification accuracy: "
        f"{classification_accuracy:.1%}"
    )

    print(
        "Evidence grounding rate: "
        f"{evidence_grounding_rate:.1%}"
    )

    print(
        "Classification-review routing accuracy: "
        f"{review_routing_accuracy:.1%}"
    )

    print(
        "Average processing time: "
        f"{average_duration:.2f} seconds"
    )


if __name__ == "__main__":
    evaluate()