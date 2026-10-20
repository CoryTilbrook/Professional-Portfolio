import re
import streamlit as st
from io import BytesIO
from html import escape

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    ListFlowable,
    ListItem,
)
from prd_agent import (
    load_agent_rules,
    ask_clarifying_questions,
    generate_feature_breakdown,
    generate_prd,
    ask_model,
)


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="AI PRD Agent",
    page_icon="📋",
    layout="wide",
)


# ==========================================
# SESSION STATE
# ==========================================

DEFAULTS = {
    "stage": "start",
    "product_idea": "",
    "require_approval": False,
    "questions_raw": "",
    "questions": [],
    "question_index": 0,
    "answers": {},
    "skipped": {},
    "breakdown": "",
    "prd": "",
}


def initialize_state():
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            if isinstance(value, dict):
                st.session_state[key] = value.copy()
            elif isinstance(value, list):
                st.session_state[key] = value.copy()
            else:
                st.session_state[key] = value


def reset_agent():
    for key in DEFAULTS:
        del st.session_state[key]

    st.rerun()


initialize_state()


# ==========================================
# LOAD RULES
# ==========================================

try:
    rules = load_agent_rules()
except Exception as error:
    st.error(f"Unable to load agent rules: {error}")
    st.stop()


# ==========================================
# QUESTION PARSING
# ==========================================

def parse_questions(raw_text):
    """
    Convert numbered discovery questions into a list.

    Supports common formats such as:
    1. Question?
    2) Question?
    Question 3: Question?

    This is a compatibility layer for the current
    Markdown-based discovery output.
    """

    raw_text = raw_text.strip()

    pattern = (
        r"(?m)^\s*(?:"
        r"(?:\*\*)?Question\s+\d+(?:\*\*)?\s*[:.)-]"
        r"|(?:\*\*)?\d+(?:\*\*)?\s*[.)]"
        r")\s*"
    )

    parts = re.split(pattern, raw_text)

    questions = []

    for part in parts:
        cleaned = part.strip()

        if cleaned:
            questions.append(cleaned)

    # Remove introductory text before the first numbered question.
    if len(questions) > 1:
        first_part = questions[0]

        if not first_part.rstrip().endswith("?"):
            questions = questions[1:]

    if not questions:
        return []

    # A single result may mean the model returned
    # unstructured text. Avoid silently treating
    # several questions as one.
    if len(questions) == 1:
        if raw_text.count("?") > 1:
            return []

    return questions


# ==========================================
# ANSWER MANAGEMENT
# ==========================================

def save_current_answer():
    index = st.session_state.question_index

    value = st.session_state.get(
        f"answer_input_{index}", ""
    ).strip()

    st.session_state.answers[index] = value

    if value:
        st.session_state.skipped[index] = False


def skip_current_question():
    index = st.session_state.question_index

    st.session_state.answers[index] = ""
    st.session_state.skipped[index] = True

    # Clear the field if the user previously
    # entered an answer.
    st.session_state[f"answer_input_{index}"] = ""

    advance_question()


def advance_question():
    index = st.session_state.question_index
    total = len(st.session_state.questions)

    if index < total - 1:
        st.session_state.question_index += 1
        st.session_state.stage = "discovery"
    else:
        st.session_state.stage = "review"

    st.rerun()


def previous_question():
    if st.session_state.question_index > 0:
        st.session_state.question_index -= 1

    st.rerun()


def build_discovery_answers():
    """
    Assemble answers in the format expected
    by the existing PRD generation functions.
    """

    lines = []

    for index, question in enumerate(
        st.session_state.questions
    ):
        answer = st.session_state.answers.get(
            index, ""
        ).strip()

        if not answer:
            answer = (
                "Pending Business Clarification. "
                "Do not assume an answer. "
                "Preserve this question in the PRD "
                "Open Questions section."
            )

        lines.append(
            f"Question {index + 1}: {question}\n"
            f"Answer: {answer}"
        )

    return "\n\n".join(lines)

# ==========================================
# Creae PRD
# ==========================================
def create_prd_pdf(markdown_text):
    """Convert the generated Markdown PRD into a PDF."""

    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Product Requirements Document",
    )

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="PRDTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=20,
            leading=24,
            spaceAfter=18,
        )
    )

    styles.add(
        ParagraphStyle(
            name="PRDHeading1",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            spaceBefore=14,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="PRDHeading2",
            parent=styles["Heading2"],
            fontSize=13,
            leading=17,
            spaceBefore=12,
            spaceAfter=6,
        )
    )

    story = []
    bullet_items = []

    def add_bullets():
        if bullet_items:
            story.append(
                ListFlowable(
                    [
                        ListItem(
                            Paragraph(item, styles["BodyText"])
                        )
                        for item in bullet_items
                    ],
                    bulletType="bullet",
                    leftIndent=18,
                )
            )
            story.append(Spacer(1, 6))
            bullet_items.clear()

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()

        if not line:
            add_bullets()
            story.append(Spacer(1, 6))
            continue

        if line.startswith("### "):
            add_bullets()
            story.append(
                Paragraph(
                    escape(line[4:]),
                    styles["PRDHeading2"],
                )
            )

        elif line.startswith("## "):
            add_bullets()
            story.append(
                Paragraph(
                    escape(line[3:]),
                    styles["PRDHeading1"],
                )
            )

        elif line.startswith("# "):
            add_bullets()
            story.append(
                Paragraph(
                    escape(line[2:]),
                    styles["PRDTitle"],
                )
            )

        elif line.startswith(("- ", "* ")):
            bullet_items.append(escape(line[2:]))

        else:
            add_bullets()

            formatted_line = escape(line)
            formatted_line = re.sub(
                r"\*\*(.+?)\*\*",
                r"<b>\1</b>",
                formatted_line,
            )
            formatted_line = re.sub(
                r"`(.+?)`",
                r"<font name='Courier'>\1</font>",
                formatted_line,
            )

            story.append(
                Paragraph(
                    formatted_line,
                    styles["BodyText"],
                )
            )
            story.append(Spacer(1, 6))

    add_bullets()
    document.build(story)

    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


# ==========================================
# HEADER
# ==========================================

st.title("AI Product Requirements Agent")

st.write(
    "Transform product ideas into structured, "
    "engineering-ready Product Requirements Documents."
)

st.divider()

if st.button("Start New PRD"):
    reset_agent()


# ==========================================
# STEP 1: PRODUCT DESCRIPTION
# ==========================================

if st.session_state.stage == "start":

    st.header("Describe Your Product")

    product_idea = st.text_area(
        "What product or capability would you like to build?",
        height=220,
        placeholder=(
            "Describe the business problem, users, "
            "workflows, objectives, and known requirements."
        ),
    )

    require_approval = st.checkbox(
        "Review and approve features and user stories "
        "before generating the PRD"
    )

    if st.button(
        "Analyze Requirements",
        type="primary"
    ):

        if not product_idea.strip():
            st.warning(
                "Please describe your product first."
            )

        else:
            st.session_state.product_idea = product_idea
            st.session_state.require_approval = (
                require_approval
            )

            with st.spinner(
                "Analyzing your product requirements..."
            ):
                try:
                    raw_questions = (
                        ask_clarifying_questions(
                            product_idea,
                            rules
                        )
                    )

                    questions = parse_questions(
                        raw_questions
                    )

                except Exception as error:
                    st.error(
                        f"Discovery failed: {error}"
                    )
                    st.stop()

            st.session_state.questions_raw = (
                raw_questions
            )

            if not questions:
                st.error(
                    "The agent returned discovery text "
                    "that could not be separated into "
                    "individual questions."
                )

                with st.expander(
                    "View the original AI response"
                ):
                    st.markdown(raw_questions)

                st.info(
                    "The current agent needs to return "
                    "numbered questions. We can improve "
                    "this by using structured AI output."
                )

                st.stop()

            st.session_state.questions = questions
            st.session_state.question_index = 0
            st.session_state.answers = {}
            st.session_state.skipped = {}
            st.session_state.stage = "discovery"

            st.rerun()


# ==========================================
# STEP 2: GUIDED DISCOVERY
# ==========================================

elif st.session_state.stage == "discovery":

    questions = st.session_state.questions

    total = len(questions)
    index = st.session_state.question_index

    st.header("Product Discovery")

    if index == 0:
        st.info(
            f"I've reviewed your requirements and "
            f"identified {total} questions that will "
            f"help me create a more complete PRD. "
            f"We'll go through them one at a time."
        )

    st.caption(
        f"Question {index + 1} of {total}"
    )

    st.progress((index + 1) / total)

    st.subheader(
        questions[index]
    )

    field_key = f"answer_input_{index}"

    if field_key not in st.session_state:
        st.session_state[field_key] = (
            st.session_state.answers.get(
                index, ""
            )
        )

    st.text_area(
        "Your answer",
        key=field_key,
        height=160,
        placeholder=(
            "Enter your answer here. "
            "You can also skip this question "
            "and return to it later."
        ),
    )

    st.caption(
        "Don't know the answer? Select "
        "'Skip for Now.' The question will "
        "remain open in the generated PRD."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        if index > 0:
            if st.button(
                "← Previous Question",
                use_container_width=True
            ):
                save_current_answer()
                previous_question()

    with col2:
        if st.button(
            "Skip for Now",
            use_container_width=True
        ):
            skip_current_question()

    with col3:
        label = (
            "Review Answers"
            if index == total - 1
            else "Next Question →"
        )

        if st.button(
            label,
            type="primary",
            use_container_width=True
        ):
            save_current_answer()
            advance_question()


# ==========================================
# STEP 3: REVIEW DISCOVERY ANSWERS
# ==========================================

elif st.session_state.stage == "review":

    st.header("Review Your Discovery Answers")

    st.write(
        "Review your responses before continuing. "
        "You can proceed even if some questions "
        "remain unanswered."
    )

    unanswered_count = 0

    for index, question in enumerate(
        st.session_state.questions
    ):

        answer = st.session_state.answers.get(
            index, ""
        ).strip()

        st.markdown(
            f"**Question {index + 1}: {question}**"
        )

        if answer:
            st.write(answer)
        else:
            unanswered_count += 1

            st.warning(
                "Pending Business Clarification"
            )

        if st.button(
            f"Edit Question {index + 1}",
            key=f"edit_{index}"
        ):
            st.session_state.question_index = index
            st.session_state.stage = "discovery"
            st.rerun()

        st.divider()

    if unanswered_count:
        st.info(
            f"{unanswered_count} question(s) remain "
            f"unanswered. They will be preserved "
            f"as open questions in the PRD."
        )

    if st.button(
        "Continue to Feature Analysis",
        type="primary"
    ):

        discovery_answers = (
            build_discovery_answers()
        )

        with st.spinner(
            "Analyzing features and user stories..."
        ):
            try:
                breakdown = (
                    generate_feature_breakdown(
                        st.session_state.product_idea,
                        st.session_state.questions_raw,
                        discovery_answers,
                        rules
                    )
                )

            except Exception as error:
                st.error(
                    f"Feature analysis failed: {error}"
                )
                st.stop()

        st.session_state.breakdown = breakdown

        if st.session_state.require_approval:
            st.session_state.stage = "approval"
        else:
            st.session_state.stage = "generate"

        st.rerun()


# ==========================================
# STEP 4: OPTIONAL FEATURE APPROVAL
# ==========================================

elif st.session_state.stage == "approval":

    st.header(
        "Review Features and User Stories"
    )

    st.markdown(
        st.session_state.breakdown
    )

    changes = st.text_area(
        "Would you like to change anything?",
        height=150
    )

    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "Approve and Continue",
            type="primary"
        ):
            st.session_state.stage = "generate"
            st.rerun()

    with col2:
        if st.button("Revise Breakdown"):

            if not changes.strip():
                st.warning(
                    "Please describe the changes."
                )

            else:
                revision_prompt = f"""
Revise the feature and story breakdown.

PRODUCT DESCRIPTION:
{st.session_state.product_idea}

DISCOVERY ANSWERS:
{build_discovery_answers()}

CURRENT BREAKDOWN:
{st.session_state.breakdown}

REQUESTED CHANGES:
{changes}

Preserve confirmed requirements.

Do not invent answers to unanswered
discovery questions.

Follow the feature and story sizing rules.

Return the complete revised breakdown.
"""

                with st.spinner(
                    "Revising feature breakdown..."
                ):
                    try:
                        revised = ask_model(
                            rules,
                            revision_prompt
                        )

                    except Exception as error:
                        st.error(
                            f"Revision failed: {error}"
                        )
                        st.stop()

                st.session_state.breakdown = revised
                st.rerun()


# ==========================================
# STEP 5: GENERATE PRD
# ==========================================

elif st.session_state.stage == "generate":

    st.header(
        "Generate Product Requirements Document"
    )

    st.write(
        "Your discovery and feature analysis "
        "are complete."
    )

    if st.button(
        "Generate PRD",
        type="primary"
    ):

        discovery_answers = (
            build_discovery_answers()
        )

        with st.spinner(
            "Generating your Product "
            "Requirements Document..."
        ):
            try:
                prd = generate_prd(
                    st.session_state.product_idea,
                    st.session_state.questions_raw,
                    discovery_answers,
                    st.session_state.breakdown,
                    rules
                )

            except Exception as error:
                st.error(
                    f"PRD generation failed: {error}"
                )
                st.stop()

        st.session_state.prd = prd
        st.session_state.stage = "complete"

        st.rerun()


# ==========================================
# STEP 6: PRD PREVIEW AND DOWNLOAD
# ==========================================

elif st.session_state.stage == "complete":

    st.header(
        "Generated Product Requirements Document"
    )

    st.success(
        "PRD generation completed."
    )

    st.markdown(
        st.session_state.prd
    )

    st.divider()

    pdf_data = create_prd_pdf(
    st.session_state.prd
)

st.download_button(
    label="Download PRD as PDF",
    data=pdf_data,
    file_name="Product_Requirements_Document.pdf",
    mime="application/pdf",
)