import pandas as pd

def parse_excel_file(filepath):
    df = pd.read_excel(filepath)
    questions = []

    for index, row in df.iterrows():
        try:
            question_type = str(row["Type"]).strip().upper()
            question_text = str(row["question"]).strip()
            correct_raw = str(row["correct_asnwer"]).strip()

            # Default structure
            question = {
                "question": question_text,
                "type": "",
                "options": [],
                "correct_answer": None
            }

            if question_type == "FILL":
                question["type"] = "text"
                question["correct_answer"] = correct_raw.strip()
            elif question_type == "MCQ":
                question["type"] = "multi"
                options = [
                    str(row.get("option_a", "")).strip(),
                    str(row.get("option_b", "")).strip(),
                    str(row.get("option_c", "")).strip(),
                    str(row.get("option_d", "")).strip()
                ]
                question["options"] = options
                index_map = {"a": 0, "b": 1, "c": 2, "d": 3}
                correct_indices = [opt.strip().lower() for opt in correct_raw.split(',')]
                question["correct_answer"] = [
                    options[index_map[c]] for c in correct_indices if c in index_map
                ]
            elif question_type == "SCQ":
                question["type"] = "single"
                options = [
                    str(row.get("option_a", "")).strip(),
                    str(row.get("option_b", "")).strip(),
                    str(row.get("option_c", "")).strip(),
                    str(row.get("option_d", "")).strip()
                ]
                question["options"] = options
                index_map = {"a": 0, "b": 1, "c": 2, "d": 3}
                answer_key = correct_raw.strip().lower()
                if answer_key in index_map:
                    question["correct_answer"] = options[index_map[answer_key]]
                else:
                    raise ValueError("Invalid SCQ answer key")
            else:
                continue  # skip unknown type

            questions.append(question)

        except Exception as e:
            print(f"❌ Error in row {index+1}: {e}")
            continue

    return questions
