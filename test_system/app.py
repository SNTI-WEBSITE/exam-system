from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from pymongo import MongoClient
import os
from .utils.parse_excel import parse_excel_file  
from dateutil import parser 

from dotenv import load_dotenv
import logging
import random

load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Use any strong string here

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

@app.route('/sntad')
def admin_panel():
    if not session.get('admin_logged_in'):
        return redirect('/login')  # 🔒 block access
    return render_template('admin.html')
@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)  # Remove login flag
    return redirect('/login')

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
    
    admin = admin_col.find_one({'personal_number': str(pn)})
    if admin:
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
        session['admin_logged_in'] = True
        session['admin_role'] = admin.get('role', 'normal')  # store role
        return jsonify({'message': 'Admin logged in'}), 200
    return jsonify({'error': 'Invalid admin credentials'}), 401



@app.route('/upload_question', methods=['POST'])
def upload_question():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        # ✅ Parse Excel file
        questions = parse_excel_file(filepath)
        if not questions:
            return jsonify({'error': 'No valid questions found in the file'}), 400

        # ✅ Delete previous questions
        question_col.delete_many({})  # 🔥 delete all old question sets

        # ✅ Insert new question set
        question_col.insert_one({
            'file_name': filename,
            'questions': questions,
            'uploaded_at': datetime.utcnow()
        })

        return jsonify({'message': f'{len(questions)} questions uploaded successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500




@app.route('/start_test_config', methods=['POST'])
def start_test_config():
    data = request.get_json()
    num = data.get('num_questions')

    if not isinstance(num, int) or num <= 0:
        return jsonify({'error': 'Invalid number of questions'}), 400

    config_col.update_one(
        {"type": "test"},
        {"$set": {
            "num_questions": num
        }},
        upsert=True
    )
    return jsonify({'message': f'Test configured with {num} questions'})



@app.route('/start_test_window', methods=['POST'])
def start_test_window():
    data = request.get_json()
    test_type = data.get('type')
    duration = int(data.get('duration', 30))  # Default to 30 minutes if not provided

    if test_type not in ['pre', 'post']:
        return jsonify({'error': 'Invalid test type'}), 400

    start_time = datetime.utcnow()
    expire_time = start_time + timedelta(minutes=duration)

    window_col.delete_many({"type": "active"})
    window_col.insert_one({
        "type": "active",
        "test_type": test_type,
        "start_time": start_time,
        "expire_time": expire_time
    })

    return jsonify({
        'message': f'{test_type.capitalize()} test window started',
        'start_time': start_time.isoformat(),
        'expire_time': expire_time.isoformat()
    })


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

from dateutil import parser  # add at top if not already

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
    expire_time = window.get("expire_time")  # ✅ get correct end time

    existing = session_col.find_one({'personal_number': pn, 'test_type': test_type})
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

    # Flatten questions from all uploaded files
    all_docs = list(question_col.find())
    all_questions = []
    for doc in all_docs:
        all_questions.extend(doc.get("questions", []))

    selected = random.sample(all_questions, min(num_qs, len(all_questions)))

    for i, q in enumerate(selected):
        q['_id'] = str(i)

    session_col.insert_one({
        "personal_number": pn,
        "name": name,
        "test_type": test_type,
        "questions": selected,
        "start_time": datetime.utcnow(),
        "end_time": expire_time,  # ✅ use correct custom duration
        "submitted": False
    })

    test_name_doc = config_col.find_one({"type": "test"})
    test_name = test_name_doc.get("test_name", "Welcome to the Exam") if test_name_doc else "Welcome to the Exam"


    return jsonify({
    "questions": selected,
    "end_time": expire_time,
    "test_type": test_type,
    "test_name": test_name
})


@app.route('/save_test_name', methods=['POST'])
def save_test_name():
    data = request.get_json()
    name = data.get("name", "Welcome to the Exam")  # Fallback default
    config_col.update_one({"type": "test"}, {"$set": {"test_name": name}}, upsert=True)
    return jsonify({"message": "Test name saved"})

@app.route('/get_test_name', methods=['GET'])
def get_test_name():
    config = config_col.find_one({"type": "test"})
    name = config.get("test_name", "Welcome to the Exam") if config else "Welcome to the Exam"
    return jsonify({"test_name": name})



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

@app.route('/add_student', methods=['POST'])
def add_student():
    data = request.get_json()
    pn = str(data.get('personal_number')).strip()
    name = data.get('name', '').strip()

    if not pn or not name:
        return jsonify({'error': 'Both personal number and name are required'}), 400

    if student_col.find_one({'personal_number': pn}):
        return jsonify({'error': 'Student already exists'}), 400

    student_col.insert_one({'personal_number': pn, 'name': name})
    return jsonify({'message': 'Student added successfully'})

@app.route('/get_students', methods=['GET'])
def get_students():
    students = list(student_col.find({}, {'_id': 0}))
    return jsonify({'students': students})

@app.route('/delete_student', methods=['POST'])
def delete_student():
    data = request.get_json()
    pn = str(data.get('personal_number')).strip()

    result = student_col.delete_one({'personal_number': pn})
    if result.deleted_count > 0:
        return jsonify({'message': f'Student {pn} deleted successfully'})
    else:
        return jsonify({'error': 'Student not found'}), 404


def evaluate_answers(questions, student_answers):
    score = 0
    for q in questions:
        qid = str(q['_id'])
        correct = q.get('correct_answer')
        if correct is None:
         continue

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
@app.route('/add_admin', methods=['POST'])
def add_admin():
    data = request.get_json()
    pn = str(data.get('personal_number')).strip()
    pw = str(data.get('password')).strip()
    
    if not pn or not pw:
        return jsonify({'error': 'Both fields are required'}), 400
    
    if admin_col.find_one({'personal_number': pn}):
        return jsonify({'error': 'Admin already exists'}), 400

    admin_col.insert_one({'personal_number': pn, 'password': pw})
    return jsonify({'message': 'Admin added successfully'}), 200

@app.route('/get_admins', methods=['GET'])
def get_admins():
    admins = list(admin_col.find({}, {'_id': 0, 'password': 0}))
    return jsonify({'admins': admins})

@app.route('/delete_admin', methods=['POST'])
def delete_admin():
    data = request.get_json()
    pn = str(data.get('personal_number')).strip()
    
    if pn == "123455":
        return jsonify({'error': 'Cannot delete Super Admin'}), 403

    result = admin_col.delete_one({'personal_number': pn})
    if result.deleted_count > 0:
        return jsonify({'message': 'Admin deleted successfully'}), 200
    else:
        return jsonify({'error': 'Admin not found'}), 404

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)