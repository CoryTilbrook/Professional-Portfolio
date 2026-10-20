from groq import Groq
import streamlit as st
from pathlib import Path
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================

MODEL = "openai/gpt-oss-120b"

client = Groq(
    api_key=st.secrets["GROQ_API_KEY"]
)

APP_DIRECTORY = Path(__file__).resolve().parent
RULES_FILE = APP_DIRECTORY / "prd_rules.md"

OUTPUT_DIR = APP_DIRECTORY / "generated_prds"


# ==========================================
# LOAD AGENT RULES
# ==========================================

def load_agent_rules():
    """
    Load the PRD agent's instructions
    from the external Markdown file.
    """

    if not RULES_FILE.is_file():
        raise FileNotFoundError(
            f"Agent rules file not found: {RULES_FILE}"
        )

    rules = RULES_FILE.read_text(encoding="utf-8")

    if not rules.strip():
        raise ValueError(
            "The PRD rules file is empty."
        )

    return rules

# ==========================================
# Send Instructions to Grog
# ==========================================
def ask_model(system_prompt, user_prompt):
    """
    Send instructions and user input
    to the Groq model.
    """

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]
    )

    return response.choices[0].message.content

# ==========================================
# USER CONFIGURATION
# ==========================================

def get_user_configuration():
    """
    Ask whether the user wants to approve
    the feature and story breakdown.
    """

    print("\n========== PRD CONFIGURATION ==========\n")

    print(
        "Would you like to review and approve "
        "the proposed feature and user story "
        "breakdown before PRD generation?"
    )

    while True:

        selection = input(
            "\nEnter Yes or No: "
        ).strip().lower()

        if selection in ["yes", "y"]:
            return True

        if selection in ["no", "n"]:
            return False

        print("Please enter Yes or No.")


# ==========================================
# PRODUCT DISCOVERY
# ==========================================

def ask_clarifying_questions(product_idea, rules):
    """
    Identify missing information before
    generating the PRD.
    """

    system_prompt = (
        rules
        + "\n\nCURRENT TASK:\n"
        "Generate a complete, detailed PRD now.\n"
        "The Streamlit application has already handled the "
        "feature approval decision.\n"
        "Treat the supplied feature and story breakdown as final.\n"
        "Do not ask for approval, confirmation, or additional input.\n"
        "Do not describe what you will generate later.\n"
        "Follow all applicable requirements in the rules file.\n"
        "Return only the complete PRD document.\n"
        "Begin directly with the PRD title.\n"
    )

    user_prompt = f"""
Review the following product description.

PRODUCT DESCRIPTION:
{product_idea}

INSTRUCTIONS:

1. Extract and preserve the requirements already provided.
2. Identify important missing information.
3. Do not ask questions already answered.
4. Ask up to five focused clarifying questions.
5. Prioritize questions that materially affect
   implementation, testing, or business value.
6. Allow unknown information to remain unresolved.
7. Do not generate the PRD.

Return only the numbered discovery questions.
"""

    return ask_model(system_prompt, user_prompt)


def collect_discovery_answers():
    """
    Collect user responses to discovery questions.
    """

    print("\n========== DISCOVERY ANSWERS ==========\n")

    print("Please answer the questions above.")
    print("You can enter 'Unknown' for missing information.")
    print("Type DONE on a new line when finished.\n")

    answers = []

    while True:

        answer = input()

        if answer.strip().upper() == "DONE":
            break

        answers.append(answer)

    return "\n".join(answers).strip()


# ==========================================
# FEATURE AND STORY BREAKDOWN
# ==========================================

def generate_feature_breakdown(
    product_idea,
    discovery_questions,
    discovery_answers,
    rules
):
    """
    Generate a proposed feature and
    user story structure.
    """

    system_prompt = (
        rules
        + "\n\nCURRENT TASK:\n"
        "Propose a feature and user story breakdown.\n"
        "Do not generate the complete PRD yet.\n"
    )

    user_prompt = f"""
Create a proposed feature and user story breakdown.

ORIGINAL PRODUCT DESCRIPTION:
{product_idea}

DISCOVERY QUESTIONS:
{discovery_questions}

DISCOVERY ANSWERS:
{discovery_answers}

REQUIREMENTS:

- Features must deliver meaningful business capabilities.
- Stories must represent cohesive, testable outcomes.
- Do not create task-level stories.
- Avoid unnecessarily granular stories.
- Preserve all confirmed requirements.
- Do not invent missing business requirements.
- Group related behaviors into appropriate stories.
- Include a short description of each proposed story.
- Identify relevant MVP or release phases.

Do not generate acceptance criteria yet.

Return the proposed feature and story structure.
"""

    return ask_model(system_prompt, user_prompt)


# ==========================================
# OPTIONAL BREAKDOWN APPROVAL
# ==========================================

def review_feature_breakdown(
    breakdown,
    product_idea,
    discovery_questions,
    discovery_answers,
    rules
):
    """
    Allow the user to approve or revise
    the proposed feature/story structure.
    """

    while True:

        print("\n========== PROPOSED FEATURES ==========\n")

        print(breakdown)

        print("\nWould you like to:")

        print("1. Approve this breakdown")
        print("2. Request changes")

        selection = input(
            "\nEnter 1 or 2: "
        ).strip()

        if selection == "1":

            print("\nFeature breakdown approved.")

            return breakdown

        elif selection == "2":

            print("\nDescribe the changes you want.")
            print("Type DONE on a new line when finished.\n")

            changes = []

            while True:

                line = input()

                if line.strip().upper() == "DONE":
                    break

                changes.append(line)

            requested_changes = "\n".join(changes).strip()

            if not requested_changes:
                print("No changes entered.")
                continue

            system_prompt = (
                rules
                + "\n\nCURRENT TASK:\n"
                "Revise the proposed feature and story breakdown.\n"
                "Do not generate the complete PRD.\n"
            )

            user_prompt = f"""
Revise the following feature and story breakdown.

ORIGINAL PRODUCT DESCRIPTION:
{product_idea}

DISCOVERY QUESTIONS:
{discovery_questions}

DISCOVERY ANSWERS:
{discovery_answers}

CURRENT BREAKDOWN:
{breakdown}

USER REQUESTED CHANGES:
{requested_changes}

Apply the requested changes.

Preserve confirmed requirements.

Maintain appropriate feature and story sizing.

Return the complete revised breakdown.
"""

            breakdown = ask_model(
                system_prompt,
                user_prompt
            )

        else:

            print("Please enter 1 or 2.")


# ==========================================
# PRD GENERATION
# ==========================================

def generate_prd(
    product_idea,
    discovery_questions,
    discovery_answers,
    feature_breakdown,
    rules
):
    """
    Generate a complete Product Requirements
    Document using the external rules.
    """

    system_prompt = (
        rules
        + "\n\nCURRENT TASK:\n"
        "Generate a complete, detailed PRD.\n"
        "Follow all requirements in the rules file.\n"
        "Return only the PRD document.\n"
    )

    user_prompt = f"""
Create a complete Product Requirements Document.

ORIGINAL PRODUCT DESCRIPTION:
{product_idea}

DISCOVERY QUESTIONS:
{discovery_questions}

DISCOVERY ANSWERS:
{discovery_answers}

FEATURE AND STORY BREAKDOWN:
{feature_breakdown}

IMPORTANT REQUIREMENTS:

1. Preserve every confirmed requirement.

2. Use the provided feature and story breakdown.

3. Do not split stories into unnecessarily
   granular implementation tasks.

4. Every story must include:
   - A user story statement.
   - Detailed functional behavior.
   - Business rules.
   - Validation requirements.
   - Relevant error handling.
   - Multiple Gherkin acceptance criteria
     when necessary.

5. Present user stories and acceptance criteria
   side-by-side in Markdown tables.

6. Include MVP and release phasing.

7. Clearly identify assumptions and open questions.

8. Do not invent business requirements,
   numerical limits, or technical constraints.

9. Do not create artificial story or feature IDs.

10. Follow every applicable instruction
    in the external PRD rules file.

11. The approval decision has already been completed
    by the application.

12. Do not ask the user to approve, confirm, or select
    anything.

13. Return the complete PRD in this response.

Generate the complete PRD.
"""

    return ask_model(system_prompt, user_prompt)


# ==========================================
# SAVE PRD
# ==========================================

def save_prd(content):
    """
    Save the generated PRD as a Markdown file.
    """

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    output_file = (
        OUTPUT_DIR / f"PRD_{timestamp}.md"
    )

    output_file.write_text(
        content,
        encoding="utf-8"
    )

    print("\nPRD saved successfully.")

    print(f"File location: {output_file}")

    return output_file


# ==========================================
# MAIN APPLICATION
# ==========================================

def main():

    print("\n===================================")
    print("          AI PRD GENERATOR")
    print("===================================\n")

    try:

        # Load the external agent instructions

        rules = load_agent_rules()

        print("PRD agent rules loaded successfully.")

        print(f"Using AI model: {MODEL}")

        # User configuration

        require_approval = get_user_configuration()

        # Collect initial product description

        print("\n========== PRODUCT DESCRIPTION ==========\n")

        print(
            "Describe the business problem, proposed solution, "
            "or product capability you want to develop."
        )

        print(
            "\nInclude any known requirements, workflows, "
            "constraints, or business objectives."
        )

        print(
            "\nType DONE on a new line when finished.\n"
        )

        description_lines = []

        while True:

            line = input()

            if line.strip().upper() == "DONE":
                break

            description_lines.append(line)

        product_idea = "\n".join(
            description_lines
        ).strip()

        if not product_idea:

            print("\nA product description is required.")

            return

        # Discovery

        print("\nAnalyzing product requirements...")

        discovery_questions = ask_clarifying_questions(
            product_idea,
            rules
        )

        print("\n========== DISCOVERY QUESTIONS ==========\n")

        print(discovery_questions)

        discovery_answers = collect_discovery_answers()

        # Generate feature/story structure

        print("\nAnalyzing feature and story structure...")

        feature_breakdown = generate_feature_breakdown(
            product_idea,
            discovery_questions,
            discovery_answers,
            rules
        )

        # Optional approval

        if require_approval:

            feature_breakdown = review_feature_breakdown(
                feature_breakdown,
                product_idea,
                discovery_questions,
                discovery_answers,
                rules
            )

        else:

            print(
                "\nFeature/story approval skipped "
                "based on your configuration."
            )

        # Generate complete PRD

        print("\nGenerating Product Requirements Document...")

        prd = generate_prd(
            product_idea,
            discovery_questions,
            discovery_answers,
            feature_breakdown,
            rules
        )

        print("\n========== GENERATED PRD ==========\n")

        print(prd)

        # Save document

        save_prd(prd)

        print(
            "\nPRD generation completed successfully."
        )

    except Exception as error:

        print(
            f"\nError running PRD Agent: {error}"
        )


# ==========================================
# APPLICATION ENTRY POINT
# ==========================================

if __name__ == "__main__":
    main()