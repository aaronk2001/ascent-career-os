"""
Interview preparation agent — generates questions and STAR answers.
"""
import os
import json

from .profile import load_profile

QUESTION_TEMPLATES = {
    "behavioral": [
        "Tell me about a time you solved a complex technical problem under pressure.",
        "Describe a situation where you had to work with a difficult team member.",
        "Give an example of when you improved an existing process.",
        "Tell me about a project where you had to learn a new technology quickly.",
        "Describe a time you caught a critical bug or system failure before it caused harm.",
    ],
    "technical": [
        "Walk me through how you would troubleshoot a PLC program that's behaving unexpectedly.",
        "How do you approach preventive maintenance planning for a robot fleet?",
        "Explain how you would set up a computer vision quality inspection system.",
        "What's your process for reading and interpreting electrical schematics?",
        "How do you ensure safety when working with collaborative robots like UR5e?",
    ],
}


def generate_prep(company: str, role: str) -> dict:
    """Generate interview questions + STAR answers for a company/role."""

    questions = []

    # Add behavioral questions with STAR answers
    for q in QUESTION_TEMPLATES["behavioral"][:3]:
        questions.append({
            "type": "behavioral",
            "question": q,
            "star_answer": generate_star_answer(q),
            "tip": "Use the STAR format: Situation, Task, Action, Result"
        })

    # Add technical questions
    for q in QUESTION_TEMPLATES["technical"][:3]:
        questions.append({
            "type": "technical",
            "question": q,
            "answer_guide": "Draw from your PLC, robotics, and CV experience",
            "tip": f"Mention specific tools: Allen Bradley, UR5e, YOLOv8, Python"
        })

    # Company-specific questions
    questions.append({
        "type": "company",
        "question": f"Why do you want to work at {company}?",
        "answer_guide": f"Research {company}'s products and connect to your robotics/automation background",
        "tip": "Show you've done research — mention their product lines or recent news"
    })

    questions.append({
        "type": "company",
        "question": f"Where do you see yourself in 5 years in a {role} role?",
        "answer_guide": "Connect to leadership in automation/AI-driven manufacturing",
        "tip": "Mention growing from hands-on engineering to technical leadership"
    })

    return {
        "company": company,
        "role": role,
        "questions": questions,
        "key_achievements": load_profile()["achievements"],
        "preparation_tips": [
            "Research the company's main products and automation challenges",
            "Prepare 2-3 stories with measurable impact (uptime, time saved, defects avoided)",
            "Be ready to whiteboard a simple PLC ladder logic program",
            "Have a GitHub project or demo ready to screen share",
        ]
    }


def generate_star_answer(question: str) -> str:
    """Template STAR answer seeded from the profile's STAR lines."""
    p = load_profile()
    situation = p["star_situation"] or "[Describe the context: team, system, scale]"
    result = p["star_result"] or "[Quantify the outcome: uptime, time saved, defects or cost avoided]"
    return (
        f"**Situation:** {situation}\n"
        "**Task:** [Describe the specific challenge related to this question]\n"
        "**Action:** [Describe the specific technical steps you took]\n"
        f"**Result:** {result}\n\n"
        "_Fill in the Situation/Task/Action with specifics from your experience._"
    )
