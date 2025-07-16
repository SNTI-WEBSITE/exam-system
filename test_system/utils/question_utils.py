# utils/question_utils.py
import random

def assign_random_questions(all_questions, count):
    return random.sample(all_questions, min(count, len(all_questions)))

def evaluate_answers(questions, submitted_answers):
    score = 0
    for q in questions:
        qid = q['question_id']
        correct = set(q['correct_answer'])
        given = set(submitted_answers.get(qid, []))

        if correct == given:
            score += 1
    return score