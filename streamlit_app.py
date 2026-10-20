import re
from datetime import datetime
from html import escape
from io import BytesIO

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from prd_agent import (
    ask_clarifying_questions,
    ask_model,
    generate_feature_breakdown,
    generate_prd,
    load_agent_rules,
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
        if key in st.session_state:
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
    """Convert numbered discovery questions into a list."""
    raw_text = raw_text.strip()
    pattern = (
        r"(?m)^\s*(?:"
        r"(?:\*\*)?Question\s+\d+(?:\*\*)?\s*[:.)-]"
        r"|(?:\*\*)?\d+(?:\*\*)?\s*[.)]"
        r")\s*"
    )
    parts = re.split(pattern, raw_text)
    questions = [part.strip() for part in parts if part.strip()]

    if len(questions) > 1 and not questions[0].rstrip().endswith("?"):
        questions = questions[1:]

    if len(questions) == 1 and raw_text.count("?") > 1:
        return []

    return questions


# ==========================================
# ANSWER MANAGEMENT
# ==========================================

def save_current_answer():
    index = st.session_state.question_index
    value = st.session_state.get(f"answer_input_{index}", "").strip()
    st.session_state.answers[index] = value
    if value:
        st.session_state.skipped[index] = False


def advance_question():
    index = st.session_state.question_index
    total = len(st.session_state.questions)
    if index < total - 1:
        st.session_state.question_index += 1
        st.session_state.stage = "discovery"
    else:
        st.session_state.stage = "review"
    st.rerun()


def skip_current_question():
    index = st.session_state.question_index
    st.session_state.answers[index] = ""
    st.session_state.skipped[index] = True
    st.session_state[f"answer_input_{index}"] = ""
    advance_question()


def previous_question():
    if st.session_state.question_index > 0:
        st.session_state.question_index -= 1
    st.rerun()


def build_discovery_answers():
    lines = []
    for index, question in enumerate(st.session_state.questions):
        answer = st.session_state.answers.get(index, "").strip()
        if not answer:
            answer = (
                "Pending Business Clarification. Do not assume an answer. "
                "Preserve this question in the PRD Open Questions section."
            )
        lines.append(f"Question {index + 1}: {question}\nAnswer: {answer}")
    return "\n\n".join(lines)


# ==========================================
# PROFESSIONAL PDF RENDERER
# ==========================================

def _normalize_markdown(text):
    """Normalize common model output without changing its meaning."""
    replacements = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2264": "<=",
        "\u2265": ">=",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _inline_markdown(text):
    """Convert safe inline Markdown into ReportLab paragraph markup."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = escape(text, quote=False)
    text = text.replace("\n", "<br/>")

    # Code must be processed before emphasis.
    text = re.sub(
        r"`([^`]+)`",
        r"<font name='Courier'>\1</font>",
        text,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
    return text


def _is_table_separator(line):
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _parse_table_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _page_header_footer(canvas, document):
    canvas.saveState()
    page_number = canvas.getPageNumber()
    width, height = letter

    canvas.setStrokeColor(colors.HexColor("#D6DCE4"))
    canvas.setLineWidth(0.5)
    canvas.line(document.leftMargin, height - 0.43 * inch, width - document.rightMargin, height - 0.43 * inch)
    canvas.line(document.leftMargin, 0.42 * inch, width - document.rightMargin, 0.42 * inch)

    canvas.setFillColor(colors.HexColor("#52606D"))
    canvas.setFont("Helvetica", 8)
    canvas.drawString(document.leftMargin, height - 0.32 * inch, "PRODUCT REQUIREMENTS DOCUMENT")
    canvas.drawRightString(width - document.rightMargin, 0.27 * inch, f"Page {page_number}")
    canvas.drawString(document.leftMargin, 0.27 * inch, "Generated by AI PRD Agent")
    canvas.restoreState()


def _build_pdf_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PRDTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=27,
            textColor=colors.HexColor("#17324D"),
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "PRDSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#52606D"),
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "PRDH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#17324D"),
            spaceBefore=14,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "PRDH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#24527A"),
            spaceBefore=11,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "PRDH3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#2F5F84"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "PRDBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.2,
            textColor=colors.HexColor("#202A33"),
            alignment=TA_LEFT,
            spaceAfter=6,
            allowWidows=0,
            allowOrphans=0,
        ),
        "small": ParagraphStyle(
            "PRDSmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=11,
            textColor=colors.HexColor("#202A33"),
        ),
        "table_header": ParagraphStyle(
            "PRDTableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.3,
            leading=10.5,
            textColor=colors.white,
            alignment=TA_LEFT,
        ),
        "table_cell": ParagraphStyle(
            "PRDTableCell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10.5,
            textColor=colors.HexColor("#202A33"),
        ),
        "code": ParagraphStyle(
            "PRDCode",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.8,
            leading=10.5,
            leftIndent=10,
            rightIndent=10,
            borderColor=colors.HexColor("#CBD5E1"),
            borderWidth=0.5,
            borderPadding=7,
            backColor=colors.HexColor("#F5F7FA"),
            spaceBefore=4,
            spaceAfter=7,
        ),
    }


def _regular_table(rows, styles, available_width):
    column_count = max(len(row) for row in rows)
    normalized = [row + [""] * (column_count - len(row)) for row in rows]

    # Favor the descriptive column in common PRD table shapes.
    if column_count == 2:
        widths = [available_width * 0.32, available_width * 0.68]
    elif column_count == 3:
        widths = [available_width * 0.22, available_width * 0.30, available_width * 0.48]
    elif column_count == 4:
        widths = [available_width * 0.12, available_width * 0.24, available_width * 0.32, available_width * 0.32]
    else:
        widths = [available_width / column_count] * column_count

    formatted = []
    for row_index, row in enumerate(normalized):
        style = styles["table_header"] if row_index == 0 else styles["table_cell"]
        formatted.append([Paragraph(_inline_markdown(cell), style) for cell in row])

    table = LongTable(
        formatted,
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24527A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#B8C4D0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
            ]
        )
    )
    return [table, Spacer(1, 8)]


def _story_table(rows, styles, available_width):
    """Render very long story/acceptance rows as readable stacked cards."""
    elements = []
    header = rows[0]

    for number, row in enumerate(rows[1:], start=1):
        story_text = row[0] if row else ""
        acceptance_text = row[1] if len(row) > 1 else ""

        card_data = [
            [Paragraph(f"Story {number}", styles["table_header"])],
            [Paragraph(f"<b>{escape(header[0])}</b><br/>{_inline_markdown(story_text)}", styles["table_cell"])],
            [Paragraph(f"<b>{escape(header[1])}</b><br/>{_inline_markdown(acceptance_text)}", styles["table_cell"])],
        ]
        card = Table(card_data, colWidths=[available_width], hAlign="LEFT")
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24527A")),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F5F7FA")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#9AAABD")),
                    ("LINEBELOW", (0, 1), (-1, 1), 0.4, colors.HexColor("#CBD5E1")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        elements.extend([card, Spacer(1, 9)])

    return elements


def _table_elements(rows, styles, available_width):
    if not rows:
        return []

    header_text = " ".join(rows[0]).lower()
    longest_cell = max((len(cell) for row in rows for cell in row), default=0)

    if len(rows[0]) == 2 and (
        "acceptance criteria" in header_text
        or "gherkin" in header_text
        or longest_cell > 900
    ):
        return _story_table(rows, styles, available_width)

    return _regular_table(rows, styles, available_width)


def create_prd_pdf(markdown_text):
    """Convert the generated Markdown PRD into a polished PDF."""
    markdown_text = _normalize_markdown(markdown_text)
    pdf_buffer = BytesIO()

    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.58 * inch,
        title="Product Requirements Document",
        author="AI PRD Agent",
    )
    styles = _build_pdf_styles()
    story = []
    lines = markdown_text.splitlines()
    index = 0
    first_heading_seen = False
    list_items = []
    list_kind = "bullet"
    code_lines = []
    in_code_block = False

    def flush_list():
        nonlocal list_items
        if not list_items:
            return
        story.append(
            ListFlowable(
                [ListItem(Paragraph(_inline_markdown(item), styles["body"]), leftIndent=12) for item in list_items],
                bulletType=list_kind,
                start="1" if list_kind == "1" else None,
                leftIndent=20,
                bulletFontName="Helvetica",
                bulletFontSize=8,
                spaceAfter=6,
            )
        )
        list_items = []

    def flush_code():
        nonlocal code_lines
        if code_lines:
            story.append(Paragraph(escape("\n".join(code_lines)).replace("\n", "<br/>"), styles["code"]))
            code_lines = []

    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()

        if line.startswith("```"):
            flush_list()
            if in_code_block:
                flush_code()
                in_code_block = False
            else:
                in_code_block = True
            index += 1
            continue

        if in_code_block:
            code_lines.append(raw_line)
            index += 1
            continue

        if line.startswith("|") and index + 1 < len(lines) and _is_table_separator(lines[index + 1].strip()):
            flush_list()
            rows = [_parse_table_row(line)]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(_parse_table_row(lines[index].strip()))
                index += 1
            story.extend(_table_elements(rows, styles, document.width))
            continue

        if not line:
            flush_list()
            story.append(Spacer(1, 3))
            index += 1
            continue

        if re.fullmatch(r"-{3,}", line):
            flush_list()
            story.extend([Spacer(1, 3), HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#D6DCE4")), Spacer(1, 4)])
            index += 1
            continue

        heading_match = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading_match:
            flush_list()
            level = len(heading_match.group(1))
            heading = heading_match.group(2).strip()
            if level == 1 and not first_heading_seen:
                story.append(Spacer(1, 0.45 * inch))
                story.append(Paragraph(_inline_markdown(heading), styles["title"]))
                story.append(Paragraph(datetime.now().strftime("Generated %B %d, %Y"), styles["subtitle"]))
                story.append(HRFlowable(width="65%", thickness=1.2, color=colors.HexColor("#24527A"), hAlign="CENTER"))
                story.append(Spacer(1, 0.25 * inch))
                first_heading_seen = True
            else:
                style = styles["h1"] if level <= 2 else styles["h2"] if level == 3 else styles["h3"]
                story.append(Paragraph(_inline_markdown(heading), style))
            index += 1
            continue

        bullet_match = re.match(r"^[-*+]\s+(.+)$", line)
        numbered_match = re.match(r"^\d+[.)]\s+(.+)$", line)
        if bullet_match or numbered_match:
            desired_kind = "bullet" if bullet_match else "1"
            if list_items and list_kind != desired_kind:
                flush_list()
            list_kind = desired_kind
            list_items.append((bullet_match or numbered_match).group(1))
            index += 1
            continue

        flush_list()

        # Treat short bold-only lines and Feature labels as subheadings.
        bold_line = re.fullmatch(r"\*\*(.+?)\*\*", line)
        if bold_line or (line.lower().startswith("feature:") and len(line) < 160):
            text = bold_line.group(1) if bold_line else line
            story.append(Paragraph(_inline_markdown(text), styles["h3"]))
        else:
            story.append(Paragraph(_inline_markdown(line), styles["body"]))
        index += 1

    flush_list()
    if in_code_block:
        flush_code()

    document.build(
        story,
        onFirstPage=_page_header_footer,
        onLaterPages=_page_header_footer,
    )
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


# ==========================================
# HEADER
# ==========================================

st.title("AI Product Requirements Agent")
st.write(
    "Transform product ideas into structured, engineering-ready "
    "Product Requirements Documents."
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
            "Describe the business problem, users, workflows, objectives, "
            "and known requirements."
        ),
    )
    require_approval = st.checkbox(
        "Review and approve features and user stories before generating the PRD"
    )

    if st.button("Analyze Requirements", type="primary"):
        if not product_idea.strip():
            st.warning("Please describe your product first.")
        else:
            st.session_state.product_idea = product_idea
            st.session_state.require_approval = require_approval
            with st.spinner("Analyzing your product requirements..."):
                try:
                    raw_questions = ask_clarifying_questions(product_idea, rules)
                    questions = parse_questions(raw_questions)
                except Exception as error:
                    st.error(f"Discovery failed: {error}")
                    st.stop()

            st.session_state.questions_raw = raw_questions
            if not questions:
                st.error(
                    "The agent returned discovery text that could not be "
                    "separated into individual questions."
                )
                with st.expander("View the original AI response"):
                    st.markdown(raw_questions)
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
            f"I've reviewed your requirements and identified {total} questions "
            "that will help create a more complete PRD."
        )

    st.caption(f"Question {index + 1} of {total}")
    st.progress((index + 1) / total)
    st.subheader(questions[index])

    field_key = f"answer_input_{index}"
    if field_key not in st.session_state:
        st.session_state[field_key] = st.session_state.answers.get(index, "")

    st.text_area(
        "Your answer",
        key=field_key,
        height=160,
        placeholder="Enter your answer here, or skip and return later.",
    )
    st.caption(
        "Don't know the answer? Select 'Skip for Now.' The question will "
        "remain open in the generated PRD."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        if index > 0 and st.button("← Previous Question", use_container_width=True):
            save_current_answer()
            previous_question()
    with col2:
        if st.button("Skip for Now", use_container_width=True):
            skip_current_question()
    with col3:
        label = "Review Answers" if index == total - 1 else "Next Question →"
        if st.button(label, type="primary", use_container_width=True):
            save_current_answer()
            advance_question()


# ==========================================
# STEP 3: REVIEW DISCOVERY ANSWERS
# ==========================================

elif st.session_state.stage == "review":
    st.header("Review Your Discovery Answers")
    st.write(
        "Review your responses before continuing. You can proceed even if "
        "some questions remain unanswered."
    )
    unanswered_count = 0

    for index, question in enumerate(st.session_state.questions):
        answer = st.session_state.answers.get(index, "").strip()
        st.markdown(f"**Question {index + 1}: {question}**")
        if answer:
            st.write(answer)
        else:
            unanswered_count += 1
            st.warning("Pending Business Clarification")

        if st.button(f"Edit Question {index + 1}", key=f"edit_{index}"):
            st.session_state.question_index = index
            st.session_state.stage = "discovery"
            st.rerun()
        st.divider()

    if unanswered_count:
        st.info(
            f"{unanswered_count} question(s) remain unanswered. They will be "
            "preserved as open questions in the PRD."
        )

    if st.button("Continue to Feature Analysis", type="primary"):
        discovery_answers = build_discovery_answers()
        with st.spinner("Analyzing features and user stories..."):
            try:
                breakdown = generate_feature_breakdown(
                    st.session_state.product_idea,
                    st.session_state.questions_raw,
                    discovery_answers,
                    rules,
                )
            except Exception as error:
                st.error(f"Feature analysis failed: {error}")
                st.stop()

        st.session_state.breakdown = breakdown
        st.session_state.stage = (
            "approval" if st.session_state.require_approval else "generate"
        )
        st.rerun()


# ==========================================
# STEP 4: OPTIONAL FEATURE APPROVAL
# ==========================================

elif st.session_state.stage == "approval":
    st.header("Review Features and User Stories")
    st.markdown(st.session_state.breakdown)
    changes = st.text_area("Would you like to change anything?", height=150)
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Approve and Continue", type="primary"):
            st.session_state.stage = "generate"
            st.rerun()

    with col2:
        if st.button("Revise Breakdown"):
            if not changes.strip():
                st.warning("Please describe the changes.")
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

Preserve confirmed requirements. Do not invent answers to unanswered
discovery questions. Follow the feature and story sizing rules.
Return the complete revised breakdown.
"""
                with st.spinner("Revising feature breakdown..."):
                    try:
                        revised = ask_model(rules, revision_prompt)
                    except Exception as error:
                        st.error(f"Revision failed: {error}")
                        st.stop()
                st.session_state.breakdown = revised
                st.rerun()


# ==========================================
# STEP 5: GENERATE PRD
# ==========================================

elif st.session_state.stage == "generate":
    st.header("Generate Product Requirements Document")
    st.write("Your discovery and feature analysis are complete.")

    if st.button("Generate PRD", type="primary"):
        discovery_answers = build_discovery_answers()
        with st.spinner("Generating your Product Requirements Document..."):
            try:
                prd = generate_prd(
                    st.session_state.product_idea,
                    st.session_state.questions_raw,
                    discovery_answers,
                    st.session_state.breakdown,
                    rules,
                )
            except Exception as error:
                st.error(f"PRD generation failed: {error}")
                st.stop()

        st.session_state.prd = prd
        st.session_state.stage = "complete"
        st.rerun()


# ==========================================
# STEP 6: PRD PREVIEW AND DOWNLOAD
# ==========================================

elif st.session_state.stage == "complete":
    st.header("Generated Product Requirements Document")
    st.success("PRD generation completed.")
    st.markdown(st.session_state.prd)
    st.divider()

    try:
        pdf_data = create_prd_pdf(st.session_state.prd)
    except Exception as error:
        st.error(f"PDF generation failed: {error}")
        st.stop()

    st.download_button(
        label="Download PRD as PDF",
        data=pdf_data,
        file_name="Product_Requirements_Document.pdf",
        mime="application/pdf",
    )
