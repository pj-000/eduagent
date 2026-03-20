"""Builtin education tools."""
from __future__ import annotations

import random
import json


def generate_math_problems(grade: int = 3, count: int = 10, operations: str = "+-") -> dict:
    """Generate math practice problems appropriate for the given grade level.

    Args:
        grade: Student grade level (1-6)
        count: Number of problems to generate
        operations: String of operations to include (+, -, *, /)
    """
    problems = []
    ranges = {1: (1, 10), 2: (1, 20), 3: (1, 50), 4: (1, 100), 5: (1, 200), 6: (1, 500)}
    lo, hi = ranges.get(grade, (1, 50))

    for i in range(count):
        op = random.choice(list(operations))
        a = random.randint(lo, hi)
        b = random.randint(lo, hi)

        if op == "-" and a < b:
            a, b = b, a
        if op == "/" :
            b = random.randint(1, max(1, hi // 5))
            a = b * random.randint(1, hi // max(1, b))

        expr = f"{a} {op} {b}"
        answer = eval(expr)
        problems.append({"id": i + 1, "problem": f"{expr} = ?", "answer": answer})

    return {"grade": grade, "count": count, "problems": problems}


def simplify_text(text: str, target_grade: int = 3) -> dict:
    """Provide guidelines for simplifying text to a target reading level.

    Args:
        text: The original text to simplify
        target_grade: Target grade level for readability
    """
    words = text.split()
    avg_word_len = sum(len(w) for w in words) / max(len(words), 1)
    sentence_count = max(text.count(".") + text.count("!") + text.count("?"), 1)
    avg_sentence_len = len(words) / sentence_count

    suggestions = []
    if avg_word_len > 5:
        suggestions.append("Use shorter, simpler words")
    if avg_sentence_len > 12:
        suggestions.append("Break long sentences into shorter ones")
    if len(words) > 100:
        suggestions.append("Consider breaking into smaller paragraphs")

    grade_vocab = {
        1: 500, 2: 1000, 3: 2000, 4: 3500, 5: 5000, 6: 7000,
    }

    return {
        "original_stats": {
            "word_count": len(words),
            "avg_word_length": round(avg_word_len, 1),
            "avg_sentence_length": round(avg_sentence_len, 1),
            "sentence_count": sentence_count,
        },
        "target_grade": target_grade,
        "target_vocab_size": grade_vocab.get(target_grade, 3000),
        "suggestions": suggestions,
        "original_text": text,
    }


def create_vocabulary_quiz(words: list[str], definitions: list[str] | None = None) -> dict:
    """Create a vocabulary matching quiz.

    Args:
        words: List of vocabulary words
        definitions: Optional list of definitions (same order as words)
    """
    if definitions and len(definitions) != len(words):
        return {"error": "Words and definitions must have the same length"}

    items = []
    shuffled_indices = list(range(len(words)))
    random.shuffle(shuffled_indices)

    for i, word in enumerate(words):
        item = {"word": word, "position": i + 1}
        if definitions:
            item["definition"] = definitions[i]
        items.append(item)

    quiz = {
        "type": "vocabulary_quiz",
        "item_count": len(words),
        "items": items,
    }

    if definitions:
        shuffled_defs = [definitions[i] for i in shuffled_indices]
        quiz["shuffled_definitions"] = [
            {"label": chr(65 + j), "definition": d}
            for j, d in enumerate(shuffled_defs)
        ]
        quiz["answer_key"] = {
            words[i]: chr(65 + shuffled_indices.index(i))
            for i in range(len(words))
        }

    return quiz


def generate_reading_comprehension(text: str, question_count: int = 3) -> dict:
    """Generate reading comprehension question templates for a given text.

    Args:
        text: The reading passage
        question_count: Number of question templates to generate
    """
    sentences = [s.strip() for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]

    question_templates = [
        "What is the main idea of this passage?",
        "Can you summarize the passage in your own words?",
        "What does the author mean by '{sentence_fragment}'?",
        "Why is '{topic}' important in this passage?",
        "How would you explain this passage to a friend?",
        "What new information did you learn from this passage?",
    ]

    questions = []
    for i in range(min(question_count, len(question_templates))):
        q = question_templates[i]
        if "{sentence_fragment}" in q and sentences:
            fragment = sentences[min(i, len(sentences) - 1)][:50]
            q = q.replace("{sentence_fragment}", fragment)
        if "{topic}" in q and sentences:
            topic = sentences[0].split()[0] if sentences[0].split() else "this topic"
            q = q.replace("{topic}", topic)
        questions.append({"id": i + 1, "question": q, "type": "open_ended"})

    return {
        "passage_length": len(text),
        "sentence_count": len(sentences),
        "questions": questions,
    }


# Registry of all builtin tools
BUILTIN_TOOLS = {
    "generate_math_problems": generate_math_problems,
    "simplify_text": simplify_text,
    "create_vocabulary_quiz": create_vocabulary_quiz,
    "generate_reading_comprehension": generate_reading_comprehension,
}
