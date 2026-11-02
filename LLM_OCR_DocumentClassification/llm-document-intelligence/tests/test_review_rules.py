import pytest
from pydantic import ValidationError

from src.classify_document import (
    DocumentClassification,
    is_evidence_grounded,
    requires_classification_review,
)


def test_grounded_known_classification_is_accepted():
    document = "ACH payment was completed."

    result = DocumentClassification(
        document_type="payment_record",
        evidence="ACH payment was completed.",
        confidence=0.95,
    )

    assert is_evidence_grounded(result, document) is True

    assert (
        requires_classification_review(
            result,
            document,
        )
        is False
    )


def test_ungrounded_evidence_routes_to_review():
    document = "ACH payment was completed."

    result = DocumentClassification(
        document_type="payment_record",
        evidence="The check cleared yesterday.",
        confidence=0.95,
    )

    assert is_evidence_grounded(result, document) is False

    assert (
        requires_classification_review(
            result,
            document,
        )
        is True
    )


def test_unknown_classification_routes_to_review():
    document = "Please review the attachment."

    result = DocumentClassification(
        document_type="unknown",
        evidence=None,
        confidence=0.0,
    )

    assert is_evidence_grounded(result, document) is True

    assert (
        requires_classification_review(
            result,
            document,
        )
        is True
    )


def test_low_confidence_routes_to_review():
    document = "Signed authorization for representation."

    result = DocumentClassification(
        document_type="proof_of_authority",
        evidence="Signed authorization for representation.",
        confidence=0.60,
    )

    assert (
        requires_classification_review(
            result,
            document,
        )
        is True
    )


def test_unknown_rejects_fabricated_evidence():
    with pytest.raises(ValidationError):
        DocumentClassification(
            document_type="unknown",
            evidence="No document content provided.",
            confidence=0.0,
        )


def test_known_type_requires_evidence():
    with pytest.raises(ValidationError):
        DocumentClassification(
            document_type="medical_record",
            evidence=None,
            confidence=0.95,
        )