# LLM Document Intelligence Lab

A local LLM-powered document-classification prototype for synthetic
claims documents.

The project uses Python, Ollama, Qwen 3 8B, Pydantic, and pytest to
demonstrate structured LLM output, grounded evidence, deterministic
review controls, adversarial evaluation, and human-in-the-loop design.

## Problem

Claims-intake workflows may receive authorizations, medical records,
medical bills, payment records, correspondence, and unsupported
documents.

A classification system must identify document types without:

- Treating medical charges as proof of payment
- Classifying referenced but missing documents
- Inventing evidence
- Following instructions embedded in document content
- Automatically accepting unsupported classifications

## Supported document types

- `proof_of_authority`
- `medical_record`
- `payment_record`
- `unknown`

## System boundaries

This component assumes that intake has already produced one logical
document per classification request.

The larger workflow is:

1. File intake
2. OCR or text extraction
3. Document segmentation
4. Document classification
5. Metadata extraction
6. Claim association
7. Workflow routing
8. Document-defect review

This project currently implements step 4 only.

## Classification controls

The classifier:

- Uses a defined business-policy prompt
- Requires structured JSON output
- Restricts document types to an allowed list
- Requires exact source evidence for known types
- Requires null evidence for unknown documents
- Validates output with Pydantic
- Rejects invalid type/evidence combinations
- Routes unknown, low-confidence, or ungrounded results to review
- Uses deterministic Python logic for review decisions

## Evaluation

The golden dataset contains 16 human-approved synthetic cases,
including:

- Medical bills containing financial language
- Payment failures and refunds
- Unsigned authorization forms
- References to documents that are not present
- Blank documents
- Mixed medical and payment terminology
- A prompt-injection attempt

Current benchmark:

- Classification accuracy: 100%
- Evidence grounding rate: 100%
- Classification-review routing accuracy: 100%
- Average local processing time: 1.57 seconds
- Evaluation cases: 16

These results demonstrate performance on the current synthetic
benchmark only. They do not establish production readiness.

## Automated tests

Six pytest tests verify:

- Acceptance of grounded known classifications
- Review routing for ungrounded evidence
- Review routing for unknown documents
- Review routing for low-confidence results
- Rejection of fabricated evidence for unknown documents
- Rejection of known classifications without evidence

Run the tests:

```powershell
python -m pytest -v