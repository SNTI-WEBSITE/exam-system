import pandas as pd

def parse_excel_file(filepath):
    df = pd.read_excel(filepath)
    questions = []

    for index, row in df.iterrows():
        try:
            question_type = str(row["Type"]).strip().upper()
            options = [
                str(row["option_a"]).strip() if pd.notna(row["option_a"]) else "",
                str(row["option_b"]).strip() if pd.notna(row["option_b"]) else "",
                str(row["option_c"]).strip() if pd.notna(row["option_c"]) else "",
                str(row["option_d"]).strip() if pd.notna(row["option_d"]) else ""
            ]

            question = {
                "question": str(row["question"]).strip(),
                "type": "text" if question_type == "TEXT" else "multi" if question_type == "MCQ" else "single"
            }

            correct_raw = str(row["correct_asnwer"]).strip()

            if question["type"] == "text":
                question["options"] = []
                question["correct_answer"] = correct_raw
            else:
                question["options"] = options
                index_map = {"a": 0, "b": 1, "c": 2, "d": 3}
                if question["type"] == "multi":
                    question["correct_answer"] = [options[index_map[ans.lower()]] for ans in correct_raw.split(',') if ans.lower() in index_map]
                else:
                    question["correct_answer"] = options[index_map[correct_raw.lower()]]

            questions.append(question)

        except Exception as e:
            print(f"❌ Error in row {index+1}: {e}")
            continue

    return questions
