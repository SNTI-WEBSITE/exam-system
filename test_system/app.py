from flask import Flask, render_template, request, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from pymongo import MongoClient
import os
from utils.parse_excel import parse_excel_file
from dotenv import load_dotenv
import logging
import random

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['test_system']
admin_col = db['admin']
student_col = db['allowed_students']
question_col = db['questions']
session_col = db['student_sessions']
config_col = db['config']
window_col = db['test_window']

@app.route('/')
def index():
    return redirect('/login')

@app.route('/login')
def login():
    return render_template('student_login.html')

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

@app.route('/test')
def test_page():
    return render_template('test.html')

@app.route('/results')
def result_page():
    return render_template('result.html')

@app.route('/check_user_type', methods=['POST'])
def check_user_type():
    data = request.get_json()
    pn = data.get('personal_number')
    if pn == '123455':
        return jsonify({'type': 'admin'})
    if student_col.find_one({'personal_number': str(pn)}):
        return jsonify({'type': 'student'})
    return jsonify({'error': 'Not registered'}), 404

@app.route('/admin_login', methods=['POST'])
def admin_login():
    data = request.get_json()
    pn = data.get('personal_number')
    pw = data.get('password')
    admin = admin_col.find_one({'personal_number': str(pn)})
    if admin and pw == admin.get('password'):
        return jsonify({'message': 'Admin logged in'}), 200
    return jsonify({'error': 'Invalid admin credentials'}), 401

@app.route('/upload_question', methods=['POST'])
def upload_question():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    try:
        questions = parse_excel_file(filepath)
        question_col.delete_many({})
        question_col.insert_many(questions)
        return jsonify({'message': f'{len(questions)} questions uploaded successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/start_test_config', methods=['POST'])
def start_test_config():
    data = request.get_json()
    num = data.get('num_questions')
    if not isinstance(num, int) or num <= 0:
        return jsonify({'error': 'Invalid number of questions'}), 400
    config_col.update_one({"type": "test"}, {"$set": {"num_questions": num}}, upsert=True)
    return jsonify({'message': f'Test configured with {num} questions per student'})

@app.route('/start_test_window', methods=['POST'])
def start_test_window():
    data = request.get_json()
    test_type = data.get('type')
    start_time = datetime.utcnow()
    expire_time = start_time + timedelta(minutes=5)
    if test_type not in ['pre', 'post']:
        return jsonify({'error': 'Invalid test type'}), 400
    window_col.delete_many({"type": "active"})
    window_col.insert_one({
        "type": "active",
        "test_type": test_type,
        "start_time": start_time,
        "expire_time": expire_time
    })
    return jsonify({'message': f'{test_type.capitalize()} test window started'})

@app.route('/student_login', methods=['POST'])
def student_login():
    data = request.get_json()
    pn = str(data.get('personal_number')).strip()
    allowed = student_col.find_one({'personal_number': pn})
    if not allowed:
        return jsonify({'error': 'You are not allowed to take the test'}), 403
    window = window_col.find_one({'type': 'active'})
    if not window:
        return jsonify({'error': 'Test window not started'}), 403
    now = datetime.utcnow()
    if not (window['start_time'] <= now <= window['expire_time']):
        return jsonify({'error': 'Test window expired'}), 403
    if window['test_type'] == 'post':
        pre_session = session_col.find_one({
            "personal_number": pn,
            "test_type": "pre",
            "submitted": True
        })
        if not pre_session:
            return jsonify({'error': 'Pre-test not submitted. Cannot take post-test'}), 403
    return jsonify({'message': 'Student logged in'}), 200

@app.route('/start_test', methods=['POST'])
def start_test():
    data = request.get_json()
    pn = str(data.get('personal_number')).strip()
    config = config_col.find_one({"type": "test"})
    num_qs = config.get("num_questions", 10)
    window = window_col.find_one({'type': 'active'})
    if not window:
        return jsonify({'error': 'No active test window'}), 403
    test_type = window.get("test_type", "pre")
    existing = session_col.find_one({'personal_number': pn, 'test_type': test_type})
    now = datetime.utcnow()
    end = now + timedelta(hours=2)
    if existing:
        if existing.get("submitted"):
            return jsonify({'error': 'Test already submitted'}), 400
        return jsonify({
            "questions": existing['questions'],
            "end_time": existing['end_time'],
            "test_type": test_type
        })
    student = student_col.find_one({'personal_number': pn})
    name = student.get('name', 'Unknown')
    all_questions = list(question_col.find())
    selected = random.sample(all_questions, min(num_qs, len(all_questions)))
    for q in selected:
        q['_id'] = str(q['_id'])
    session_col.insert_one({
        "personal_number": pn,
        "name": name,
        "test_type": test_type,
        "questions": selected,
        "start_time": now,
        "end_time": end,
        "submitted": False
    })
    return jsonify({
        "questions": selected,
        "end_time": end,
        "test_type": test_type
    })

@app.route('/submit_test', methods=['POST'])
def submit_test():
    data = request.get_json()
    pn = str(data.get('personal_number')).strip()
    answers = data.get('answers')
    session = session_col.find_one({'personal_number': pn, 'submitted': False})
    if not session:
        return jsonify({'error': 'Session not found or already submitted'}), 404
    score = evaluate_answers(session['questions'], answers)
    session_col.update_one(
        {"personal_number": pn, "test_type": session['test_type']},
        {"$set": {
            "responses": answers,
            "score": score,
            "submitted": True
        }}
    )
    return jsonify({'message': 'Test submitted successfully', 'score': score})

@app.route('/get_results', methods=['GET'])
def get_results():
    submitted = list(session_col.find({"submitted": True}))
    combined = {}
    for entry in submitted:
        pn = entry['personal_number']
        name = entry.get("name", "Unknown")
        score = entry.get("score", 0)
        test_type = entry.get("test_type", "pre")
        if pn not in combined:
            combined[pn] = {"personal_number": pn, "name": name, "pre": None, "post": None}
        if test_type == "pre":
            combined[pn]["pre"] = score
        elif test_type == "post":
            combined[pn]["post"] = score
    results = []
    for val in combined.values():
        pre = val["pre"]
        post = val["post"]
        index = None
        if pre is not None and post is not None and pre != 100:
            index = round((post - pre) / (100 - pre), 2)
        results.append({
            "personal_number": val["personal_number"],
            "name": val["name"],
            "pre_score": pre,
            "post_score": post,
            "learning_index": index
        })
    return jsonify({'results': results})

@app.route('/delete_result', methods=['POST'])
def delete_result():
    data = request.get_json()
    pn = str(data.get('personal_number')).strip()
    if not pn:
        return jsonify({'error': 'Personal number is required'}), 400
    result = session_col.delete_many({'personal_number': pn})
    if result.deleted_count > 0:
        return jsonify({'message': f"Deleted {result.deleted_count} test result(s) for {pn}"}), 200
    else:
        return jsonify({'error': f"No results found for {pn}"}), 404
        @app.route('/log_tab_switch', methods=['POST'])
        def log_tab_switch():
         data = request.get_json()
    pn = str(data.get('personal_number')).strip()

    result = session_col.update_one(
        {'personal_number': pn, 'submitted': False},
        {'$set': {'tab_switch_detected': True}}
    )

    if result.modified_count:
        return jsonify({'message': 'Tab switch logged'}), 200
    else:
        return jsonify({'error': 'Session not found or already submitted'}), 404

def evaluate_answers(questions, student_answers):
    score = 0
    for q in questions:
        qid = str(q['_id'])
        correct = q['correct_answer']
        user_ans = student_answers.get(qid)
        if q['type'] == 'multi':
            if isinstance(correct, str):
                correct = [c.strip() for c in correct.split(',')]
            if isinstance(user_ans, str):
                user_ans = [u.strip() for u in user_ans.split(',')]
            if sorted(user_ans) == sorted(correct):
                score += 1
        else:
            if isinstance(correct, list) and len(correct) == 1:
                correct = correct[0]
            if isinstance(user_ans, list) and len(user_ans) == 1:
                user_ans = user_ans[0]
            if user_ans and correct and str(user_ans).strip().lower() == str(correct).strip().lower():
                score += 1
    return score

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)
