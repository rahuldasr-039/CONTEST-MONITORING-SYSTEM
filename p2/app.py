from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# --- IMPORT SCRAPER FUNCTIONS ---
# Ensure 'scrapers.py' is in the same directory
from scrapers import get_all_stats, get_detailed_stats, check_contest_participation

app = Flask(__name__)
# SECURITY NOTE: In a real deployment, use a secure random environment variable
app.config['SECRET_KEY'] = 'academic_monitor_secret_key' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ==========================================
# DATABASE MODELS
# ==========================================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student', 'mentor', 'hod', 'incharge'
    dept_code = db.Column(db.String(10), nullable=False) # e.g., 'CSE', 'ECE'
    
    # Specific Fields
    year_of_study = db.Column(db.Integer, nullable=True)  # For Students
    incharge_year = db.Column(db.Integer, nullable=True)  # For Mentors (Assigned Year)
    is_approved = db.Column(db.Boolean, default=False)    # Admin Approval Status
    
    # Coding Platform Handles
    cf_handle = db.Column(db.String(50)) # Codeforces
    lc_handle = db.Column(db.String(50)) # LeetCode
    cc_handle = db.Column(db.String(50)) # CodeChef

    # Relationships
    # This allows 'user.works' to access assigned work items

class Contest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    link = db.Column(db.String(200), nullable=False)
    platform = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Work(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    link = db.Column(db.String(200), nullable=False)
    platform = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='Pending')  # 'Pending' or 'Submitted'
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationship to access Student Name in Monitor View (e.g., work.user.name)
    user = db.relationship('User', backref=db.backref('works', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==========================================
# ROUTES
# ==========================================

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            if not user.is_approved:
                flash('Your account is pending approval from the Department Head or Mentor.', 'warning')
                return redirect(url_for('login'))
                
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Login Failed. Please check your credentials.', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form.get('password'), method='pbkdf2:sha256')
        
        # Handle Role Specific Fields
        role = request.form.get('role')
        incharge_year = None
        year_of_study = None
        
        if role == 'mentor':
            incharge_year = request.form.get('incharge_year') 
        elif role == 'student':
            year_of_study = request.form.get('year_of_study')

        new_user = User(
            name=request.form.get('name'),
            email=request.form.get('email'),
            password=hashed_pw,
            role=role,
            dept_code=request.form.get('dept_code'),
            year_of_study=year_of_study,
            incharge_year=incharge_year,
            cf_handle=request.form.get('cf'),
            lc_handle=request.form.get('lc'),
            cc_handle=request.form.get('cc'),
            is_approved=False  # New users require approval
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please wait for approval.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Error: Email already exists or invalid data provided.', 'danger')
            return redirect(url_for('register'))
        
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    # --- 1. Basic Stats for Current User ---
    user_stats = get_all_stats(current_user)
    
    # --- 2. Fetch Assignments (Work) ---
    assigned_work = Work.query.filter_by(student_id=current_user.id).all()
    
    # --- 3. AUTO-UPDATE LOGIC ---
    # Automatically checks if 'Pending' assignments have been completed
    updated_count = 0
    if current_user.role == 'student':
        for work in assigned_work:
            if work.status == 'Pending':
                # Scraper function verifies attendance
                has_attended = check_contest_participation(current_user, work.name, work.platform)
                
                if has_attended:
                    print(f"System: Auto-updating {work.name} to Submitted for {current_user.name}")
                    work.status = 'Submitted'
                    updated_count += 1
        
        if updated_count > 0:
            db.session.commit()
            flash(f'{updated_count} assignments marked as Completed automatically.', 'success')
    # -------------------------------------------

    # --- 4. Role-Based Data Loading ---
    approvals = []
    managed_contests = []
    dept_students = []
    dept_mentors = []
    mentor_students = []
    admin_report = {}

    # Faculty Shared Data
    if current_user.role in ['hod', 'mentor', 'incharge']:
        managed_contests = Contest.query.filter_by(created_by=current_user.id).all()
        
        if current_user.role == 'hod':
            approvals = User.query.filter_by(dept_code=current_user.dept_code, is_approved=False).all()
        elif current_user.role == 'mentor':
             approvals = User.query.filter_by(dept_code=current_user.dept_code, year_of_study=current_user.incharge_year, role='student', is_approved=False).all()
        elif current_user.role == 'incharge':
            approvals = User.query.filter_by(is_approved=False).all()

    # HOD View
    if current_user.role == 'hod':
        dept_students = User.query.filter_by(dept_code=current_user.dept_code, role='student', is_approved=True).all()
        dept_mentors = User.query.filter_by(dept_code=current_user.dept_code, role='mentor').all()
        for s in dept_students:
            s.stats = get_all_stats(s)

    # Mentor View
    if current_user.role == 'mentor':
        mentor_students = User.query.filter_by(dept_code=current_user.dept_code, year_of_study=current_user.incharge_year, role='student', is_approved=True).all()
        for s in mentor_students:
            s.stats = get_all_stats(s)

    # Incharge View
    if current_user.role == 'incharge':
        departments = db.session.query(User.dept_code).distinct().all()
        for dept in departments:
            d_code = dept[0]
            if d_code:
                hod = User.query.filter_by(dept_code=d_code, role='hod').first()
                mentors = User.query.filter_by(dept_code=d_code, role='mentor').all()
                students = User.query.filter_by(dept_code=d_code, role='student').all()
                
                for s in students: s.stats = get_all_stats(s)
                
                admin_report[d_code] = {
                    'hod': hod,
                    'mentors': mentors,
                    'students': students
                }

    return render_template('dashboard.html', 
                           user=current_user, 
                           user_stats=user_stats, 
                           assigned_work=assigned_work,
                           approvals=approvals,
                           managed_contests=managed_contests,
                           dept_students=dept_students,
                           dept_mentors=dept_mentors,
                           mentor_students=mentor_students,
                           admin_report=admin_report)

@app.route('/approve/<int:user_id>')
@login_required
def approve_user(user_id):
    user_to_approve = User.query.get_or_404(user_id)
    is_authorized = False
    
    # Authorization Logic
    if current_user.role == 'hod':
        if user_to_approve.dept_code == current_user.dept_code:
            is_authorized = True
            
    elif current_user.role == 'mentor':
        if (user_to_approve.dept_code == current_user.dept_code and 
            user_to_approve.role == 'student' and 
            user_to_approve.year_of_study == current_user.incharge_year):
            is_authorized = True
            
    elif current_user.role == 'incharge':
        is_authorized = True

    if is_authorized:
        user_to_approve.is_approved = True
        db.session.commit()
        flash(f'User {user_to_approve.name} has been authorized.', 'success')
    else:
        flash('Unauthorized: You do not have permission to approve this user.', 'danger')
        
    return redirect(url_for('dashboard'))

@app.route('/student/<int:user_id>')
@login_required
def student_detail(user_id):
    student = User.query.get_or_404(user_id)
    detailed_stats = get_detailed_stats(student)
    return render_template('student_detail.html', student=student, stats=detailed_stats)

@app.route('/create_contest', methods=['POST'])
@login_required
def create_contest():
    if current_user.role != 'hod':
        flash('Permission Denied: Only HODs can assign contests.', 'danger')
        return redirect(url_for('dashboard'))
        
    name = request.form.get('name')
    link = request.form.get('link')
    platform = request.form.get('platform')
    date = request.form.get('date')
    
    # 1. Create Contest Record
    contest = Contest(name=name, link=link, platform=platform, date=date, created_by=current_user.id)
    db.session.add(contest)
    
    # 2. Assign Work to All Students in Dept
    target_students = User.query.filter_by(dept_code=current_user.dept_code, role='student', is_approved=True).all()
    
    count = 0
    for s in target_students:
        work = Work(name=name, link=link, platform=platform, date=date, student_id=s.id, status='Pending')
        db.session.add(work)
        count += 1
        
    db.session.commit()
    flash(f'Assignment "{name}" created and assigned to {count} students.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/monitor/<int:contest_id>')
@login_required
def contest_monitor(contest_id):
    contest = Contest.query.get_or_404(contest_id)
    
    # Find assignments for this contest within the viewer's department
    assignments = Work.query.join(User).filter(
        Work.name == contest.name, 
        Work.platform == contest.platform,
        User.dept_code == current_user.dept_code
    ).all()
    
    return render_template('contest_monitor.html', contest=contest, assignments=assignments)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)