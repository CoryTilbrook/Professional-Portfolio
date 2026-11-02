from typing import Literal

from ollama import chat
from pydantic import BaseModel, Field, model_validator


class DocumentClassification(BaseModel):
    """Structured classification returned by the LLM."""

    document_type: Literal[
        "proof_of_authority",
        "medical_record",
        "payment_record",
        "unknown",
    ]
    evidence: str | None
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_evidence_policy(
        self,
    ) -> "DocumentClassification":
        """Enforce evidence rules for known and unknown types."""

        if self.document_type == "unknown":
            if self.evidence is not None:
                raise ValueError(
                    "Unknown classifications must have null evidence."
                )

        elif not self.evidence or not self.evidence.strip():
            raise ValueError(
                "Known classifications require evidence."
            )

        return self


DOCUMENT_TEXT = """
Claim CLM-1042 includes a signed authorization allowing
Jordan Lee to act on behalf of the claimant.
"""


SYSTEM_PROMPT = """
You classify one logical claim document at a time.

The intake process has already separated files containing multiple
logical documents. Classify only the supplied document.

Allowed document types:

1. proof_of_authority
   A document authorizing a person or organization to act for a
   claimant. Examples include a power of attorney, representation
   authorization, or signed authorization form.

2. medical_record
   A document describing healthcare services, diagnoses, treatment,
   medical providers, medical charges, or patient care. Medical bills
   and healthcare invoices are medical records, even when they contain
   charges, balances, or an amount due.

3. payment_record
   A document whose primary purpose is to confirm or report that money
   moved or that a payment transaction changed status. Examples include
   a cleared check, ACH confirmation, payment receipt, refund
   confirmation, remittance record, voided payment, or returned payment.

4. unknown
   Use when the document does not contain enough evidence to select one
   of the other categories.

Decision rules:

1. Classify by the document's primary business purpose, not isolated
   keywords such as "bill," "amount," "paid," or "balance."

2. A medical bill is a medical_record, not a payment_record.

3. An amount due or charge does not prove that a payment occurred.

4. Use payment_record only when the document provides evidence of an
   actual payment transaction or payment-status event.

5. If a medical document contains payment information, select
   medical_record when its primary purpose is to document patient care
   or provider charges.

6. Classify the document that is actually present, not another document
   that the text mentions, references, requests, or promises to provide.

7. A cover letter, status message, or correspondence stating that an
   authorization will be sent later is not proof_of_authority.

8. References to missing, future, expected, or attached documents do
   not make the current document that document type.

9. Use only information found in the supplied document.

10. Do not invent missing information.

11. For proof_of_authority, medical_record, or payment_record, evidence
   must be a short exact quote copied from the supplied document.

12. For unknown, evidence must be null.

13. If no allowed classification is supported by evidence, return
    unknown with null evidence.
"""


def classify_document(
    document_text: str,
) -> DocumentClassification:
    """Classify one pre-segmented logical document."""

    response = chat(
        model="qwen3:8b",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": document_text,
            },
        ],
        format=DocumentClassification.model_json_schema(),
        think=False,
        options={"temperature": 0},
    )

    return DocumentClassification.model_validate_json(
        response.message.content
    )


def is_evidence_grounded(
    result: DocumentClassification,
    document_text: str,
) -> bool:
    """Check evidence against the source document."""

    if result.document_type == "unknown":
        return result.evidence is None

    if result.evidence is None:
        return False

    normalized_evidence = " ".join(
        result.evidence.lower().split()
    )
    normalized_document = " ".join(
        document_text.lower().split()
    )

    return normalized_evidence in normalized_document


def requires_classification_review(
    result: DocumentClassification,
    document_text: str,
) -> bool:
    """Apply deterministic classification-review rules."""

    return (
        result.document_type == "unknown"
        or result.confidence < 0.80
        or not is_evidence_grounded(
            result,
            document_text,
        )
    )


if __name__ == "__main__":
    classification = classify_document(DOCUMENT_TEXT)

    needs_review = requires_classification_review(
        classification,
        DOCUMENT_TEXT,
    )

    print(classification.model_dump_json(indent=2))

    print(
        "Needs classification review: "
        f"{needs_review}"
    )