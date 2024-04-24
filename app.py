from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from datetime import datetime
import hashlib
from flask_mail import Mail
from flask_mail import Message
from datetime import datetime
from pymongo.errors import PyMongoError
import uuid
from werkzeug.utils import secure_filename
import os

from flask import send_file







app = Flask(__name__)

app.secret_key = 'your_secret_key'

# MongoDB Connection
client = MongoClient('mongodb://localhost:27017/')
db = client['at']
employee_collection = db['employee']
attendance_collection = db['attendance']

UPLOAD_FOLDER = 'uploads'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

app.config['MAIL_SERVER'] = 'your_email_server'
app.config['MAIL_PORT'] = 465  # For SSL
app.config['MAIL_USERNAME'] = 'your_email_username'
app.config['MAIL_PASSWORD'] = 'your_email_password'
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mail = Mail(app)




def send_registration_email(name, email):
    msg = Message('Registration Confirmation', recipients=[email])
    msg.body = f'Hello {name},\n\nThank you for registering. Your employee ID is: {generate_employee_id(name, email)}'
    mail.send(msg)

# Function to generate a unique employee ID
def generate_employee_id(name, email):
    # Combine name and email
    data = name + email
    # Hash the combined data
    hashed_data = hashlib.md5(data.encode()).hexdigest()
    # Take the first 6 characters to create a unique ID
    employee_id = hashed_data[:6].upper()  # Convert to uppercase for consistency
    return employee_id

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        employee_id = request.form['employee_id']
        password = request.form['password']  # Get the password from the form
        employee = employee_collection.find_one({'employee_id': employee_id})
        if employee and employee.get('password') == password:
            # Check if the employee is an HR employee (you need to adjust this condition based on your HR identification logic)
            if employee.get('is_hr', False):
                # Set admin session if the employee is an HR employee
                session['admin'] = employee_id
                return redirect(url_for('admin_dashboard'))
            else:
                # Set employee session if the employee is not an HR employee
                session['employee_id'] = employee_id
                employee_collection.update_one({'employee_id': employee_id}, {'$set': {'logged_in': 1}})

                return redirect(url_for('dashboard'))
        else:
            return 'Invalid Employee ID or Password'
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'employee_id' in session:
        employee_id = session['employee_id']
        employee = employee_collection.find_one({'employee_id': employee_id})
        # Fetch attendance records for the logged-in employee
        attendance_records = attendance_collection.find({'employee_id': employee_id})
        employee = employee_collection.find_one({'employee_id': employee_id})
        admin_name = employee.get('name', 'Admin')
        return render_template('dashboard.html', employee=employee, attendance_records=attendance_records,admin_name=admin_name,admin_id=employee_id)
    else:
        return redirect(url_for('login'))
    

@app.route('/mark_attendance', methods=['GET'])
def mark_attendance():
    if 'employee_id' in session:
        employee_id = session['employee_id']
        today = datetime.combine(datetime.now().date(), datetime.min.time())
        existing_attendance = attendance_collection.find_one({'employee_id': employee_id, 'date': today})
        if existing_attendance:
            return 'Attendance already marked for today'
        
        attendance_data = {
            'employee_id': employee_id,
            'date': today,
            'time_in': datetime.now()
        }
        attendance_collection.insert_one(attendance_data)
        return 'Attendance marked successfully'
    else:
        return 'Not logged in', 403
    


@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'admin' in session:
        if request.method == 'POST':
            search_query = request.form['search_query']
            # Query the employee collection to search for employees matching the search query
            employees = list(employee_collection.find({'$or': [{'employee_id': search_query}, {'name': search_query}]}))
            # If employee found, retrieve attendance data for that employee
            if employees:
                employee_id = employees[0]['employee_id']
                attendance_data = list(attendance_collection.find({'employee_id': employee_id}))
                return render_template('admin_dashboard.html', attendance_data=attendance_data, search_query=search_query)
            else:
                return render_template('admin_dashboard.html', message='No employee found for the given query')
        else:
            admin_id = session['admin']
            admin = employee_collection.find_one({'employee_id': admin_id})
            admin_name = admin.get('name', 'Admin')
            return render_template('admin_dashboard.html',admin_name=admin_name,admin_id=admin_id)
    else:
        return redirect(url_for('admin_login'))
    
@app.route('/num_present_employees', methods=['GET'])
def num_present_employees():
    if 'admin' in session:
        # Calculate the number of employees present today
        today_date =  datetime.combine(datetime.now().date(), datetime.min.time())
        present_employees = attendance_collection.distinct('employee_id', {'date': today_date})
        num_present_employees = len(present_employees)
        print(num_present_employees)
        return jsonify({'num_present_employees': num_present_employees})
    else:
        return jsonify({'error': 'Unauthorized'}), 403
    

@app.route('/num_logged_in_employees', methods=['GET'])
def num_logged_in_employees():
    if 'admin' in session:
        try:
            # Count the number of logged-in employees in the database
            num_logged_in_employees = employee_collection.count_documents({'logged_in': 1})
            return jsonify({'num_logged_in_employees': num_logged_in_employees})
        except PyMongoError as e:
            return jsonify({'error': str(e)}), 500  # Internal Server Error
    else:
        return jsonify({'error': 'Unauthorized'}), 403
    

@app.route('/', methods=['POST','GET'])
def index():
    return redirect(url_for('login'))


@app.route('/logout', methods=['POST','GET'])
def logout():
    # Retrieve employee ID from session
    employee_id = session.get('employee_id')
    if employee_id:
        # Update the login status in the database
        employee_collection.update_one({'employee_id': employee_id}, {'$set': {'logged_in': 0}})
        # Remove employee from session
        session.pop('employee_id')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        
        # Check if the POST request has the file part
        if 'resume' not in request.files:
            return 'No file part', 400
        
        resume_file = request.files['resume']
        
        # If user does not select file, browser also
        # submit an empty part without filename
        if resume_file.filename == '':
            return 'No selected file', 400
        
        # Check if the file is a PDF
        if not resume_file.filename.endswith('.pdf'):
            return 'File should be a PDF', 400
        
        # Generate unique employee ID
        employee_id = generate_employee_id(name, email)
        
        # Check if the employee ID already exists
        existing_employee = employee_collection.find_one({'employee_id': employee_id})
        if existing_employee:
            return 'Employee ID already exists. Please try again.'
        
        # Save the uploaded resume
        resume_filename = f"{employee_id}.pdf"
        resume_path = os.path.join(app.config['UPLOAD_FOLDER'], resume_filename)
        resume_file.save(resume_path)
        
        # Proceed with registration
        employee_data = {
            'employee_id': employee_id,
            'name': name,
            'email': email,
            'password': password,
            'resume_path': resume_path  # Add resume path to employee data
        }
        
        employee_collection.insert_one(employee_data)
        
        # send_registration_email(name, email)
        
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/admin_all_employees', methods=['GET'])
def admin_all_employees():
    if 'admin' in session:
        search_query = request.args.get('search_query', '')
        
        if search_query:
            # Search employees by name or employee_id
            employees = list(employee_collection.find({
                '$or': [
                    {'name': {'$regex': search_query, '$options': 'i'}},  # Case-insensitive search by name
                    {'employee_id': search_query}
                ]
            }))
        else:
            # Retrieve all employees from the database
            employees = list(employee_collection.find())
        
        return render_template('admin_all_employees.html', employees=employees, search_query=search_query)
    else:
        return redirect(url_for('admin_login'))



@app.route('/resume/<employee_id>', methods=['GET'])
def download_resume(employee_id):
    # Find the employee by employee_id to get the resume path
    employee = employee_collection.find_one({'employee_id': employee_id})
    
    if not employee or not employee.get('resume_path'):
        return 'Resume not found', 404
    
    resume_path = employee['resume_path']
    return send_file(resume_path, as_attachment=True)
    

@app.route('/admin_details/<employee_id>', methods=['GET'])
def admin_details(employee_id):
    if 'admin' in session:
        # Retrieve employee details
        employee = employee_collection.find_one({'employee_id': employee_id})
        if not employee:
            return 'Employee not found', 404
        
        # Retrieve attendance records for the employee
        attendance_records = list(attendance_collection.find({'employee_id': employee_id}))
        
        # Retrieve quiz records for the employee
        quiz_records = employee.get('quiz_records', [])
        
        return render_template('admin_details.html', employee=employee, attendance_records=attendance_records, quiz_records=quiz_records)
    else:
        return redirect(url_for('admin_login'))



# Define your quiz data
quiz_data = { "A12":[{
        'id': 1,
        'question': 'What is the capital of France?',
        'options': [
            {'id': 'paris', 'text': 'Paris'},
            {'id': 'london', 'text': 'London'},
            {'id': 'berlin', 'text': 'Berlin'},
            {'id': 'rome', 'text': 'Rome'}
        ],
        'correct_answer': 'paris'
    },
    {
        'id': 2,
        'question': 'Who wrote "To Kill a Mockingbird"?',
        'options': [
            {'id': 'harper-lee', 'text': 'Harper Lee'},
            {'id': 'mark-twain', 'text': 'Mark Twain'},
            {'id': 'jane-austen', 'text': 'Jane Austen'},
            {'id': 'george-orwell', 'text': 'George Orwell'}
        ],
        'correct_answer': 'harper-lee'
    }],
    "A13":[{
        'id': 1,
        'question': 'What is the capital of pachora?',
        'options': [
            {'id': 'paris', 'text': 'Paris'},
            {'id': 'london', 'text': 'London'},
            {'id': 'berlin', 'text': 'Berlin'},
            {'id': 'rome', 'text': 'Rome'}
        ],
        'correct_answer': 'paris'
    },
    {
        'id': 2,
        'question': 'Who wrote "To Kill a Mockingbird"?',
        'options': [
            {'id': 'harper-lee', 'text': 'Harper Lee'},
            {'id': 'mark-twain', 'text': 'Mark Twain'},
            {'id': 'jane-austen', 'text': 'Jane Austen'},
            {'id': 'george-orwell', 'text': 'George Orwell'}
        ],
        'correct_answer': 'harper-lee'
    }]}



@app.route('/quiz/<quiz_id>', methods=['GET', 'POST'])
def quiz(quiz_id):
    if request.method == 'GET':
        employee_id = session.get('employee_id')

        employee = employee_collection.find_one({'employee_id': employee_id})
        if employee and any(record['quiz_id'] == quiz_id for record in employee.get('quiz_records', [])):
            return render_template("submit.html")
        return render_template('quiz.html', quiz_data=quiz_data[quiz_id],quiz_id=quiz_id)
    elif request.method == 'POST':
        employee_id = session.get('employee_id')
        answers = {}
        score = 0
        
        for question in quiz_data[quiz_id]:
            question_id = question['id']
            selected_option = request.form.get('answer{}'.format(question_id))
            answers[question_id] = selected_option
            if selected_option == question['correct_answer']:
                score += 1
        update_employee_record(employee_id,score,quiz_id)
        return jsonify({'message': 'Quiz submitted successfully', 'score': score})






@app.route('/update_quiz_record/<employee_id>/<score>/<quiz_id>', methods=['GET'])
def update_employee_record(employee_id, score,quiz_id):
    # Convert score to integer
    score = int(score)

    # Get current date and time
    submission_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Update the employee's record in the database with the score and submission date
    query = {'employee_id': employee_id}
    update = {'$push': {'quiz_records': {'quiz_id':quiz_id,'score': score, 'submission_date': submission_date}}}
    employee_collection.update_one(query, update)

    return jsonify({'message': 'Quiz record updated successfully'})

if __name__ == '__main__':
    app.run(debug=True)