import os
import csv
from io import StringIO
from flask import Flask, render_template, redirect, url_for, request, flash, make_response
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
    password = db.Column(db.String(200), nullable=False)
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

class Contest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    link = db.Column(db.String(300), nullable=False)
    platform = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(50), nullable=False)
    dept_code = db.Column(db.String(10), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Work(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    link = db.Column(db.String(300), nullable=False)
    platform = db.Column(db.String(50), nullable=False)
    date = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='Pending')  # 'Pending' or 'Submitted'
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationship to access Student Name in Monitor View (e.g., work.user.name)
    user = db.relationship('User', backref=db.backref('works', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ==========================================
# AUTHENTICATION ROUTES
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
        if User.query.filter_by(email=request.form.get('email')).first():
            flash('Error: Email already registered.', 'danger')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(request.form.get('password'), method='pbkdf2:sha256')
        
        # Handle Role Specific Fields
        role = request.form.get('role')
        incharge_year = request.form.get('incharge_year') if role == 'mentor' else None
        year_of_study = request.form.get('year_of_study') if role == 'student' else None

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
            is_approved=False
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please wait for approval.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'danger')
            return redirect(url_for('register'))
        
    return render_template('register.html')

# ==========================================
# DASHBOARD
# ==========================================

@app.route('/dashboard')
@login_required
def dashboard():
    user_stats = None
    assigned_work = []
    
    # --- 1. STUDENT VIEW ---
    if current_user.role == 'student':
        user_stats = get_all_stats(current_user)
        pending_work = Work.query.filter_by(student_id=current_user.id, status='Pending').all()
        updated_count = 0
        for work in pending_work:
            if check_contest_participation(current_user, work.name, work.platform):
                work.status = 'Submitted'
                updated_count += 1
        if updated_count > 0:
            db.session.commit()
            flash(f'{updated_count} assignments automatically verified!', 'success')
            
        assigned_work = Work.query.filter_by(student_id=current_user.id).all()

    # --- 2. FACULTY VIEW ---
    approvals = []
    managed_contests = []
    dept_students = []
    dept_mentors = []
    mentor_students = []
    admin_report = {}

    if current_user.role in ['hod', 'mentor', 'incharge']:
        if current_user.role != 'incharge':
            managed_contests = Contest.query.filter_by(dept_code=current_user.dept_code).all()
        else:
            managed_contests = Contest.query.all()
        
        if current_user.role == 'hod':
            approvals = User.query.filter_by(dept_code=current_user.dept_code, is_approved=False).all()
            dept_students = User.query.filter_by(dept_code=current_user.dept_code, role='student', is_approved=True).all()
            dept_mentors = User.query.filter_by(dept_code=current_user.dept_code, role='mentor').all()
            for s in dept_students: s.stats = get_all_stats(s)

        elif current_user.role == 'mentor':
            approvals = User.query.filter_by(dept_code=current_user.dept_code, year_of_study=current_user.incharge_year, role='student', is_approved=False).all()
            mentor_students = User.query.filter_by(dept_code=current_user.dept_code, year_of_study=current_user.incharge_year, role='student', is_approved=True).all()
            for s in mentor_students: s.stats = get_all_stats(s)

        elif current_user.role == 'incharge':
            approvals = User.query.filter_by(is_approved=False).all()
            departments = db.session.query(User.dept_code).distinct().all()
            for (d_code,) in departments:
                if d_code:
                    students = User.query.filter_by(dept_code=d_code, role='student', is_approved=True).all()
                    for s in students: s.stats = get_all_stats(s)
                    admin_report[d_code] = {
                        'hod': User.query.filter_by(dept_code=d_code, role='hod').first(),
                        'mentors': User.query.filter_by(dept_code=d_code, role='mentor').all(),
                        'students': students
                    }

    return render_template('dashboard.html', 
                           user=current_user, user_stats=user_stats, assigned_work=assigned_work,
                           approvals=approvals, managed_contests=managed_contests,
                           dept_students=dept_students, dept_mentors=dept_mentors,
                           mentor_students=mentor_students, admin_report=admin_report)


# ==========================================
# ACTIONS (APPROVAL, CREATE, MONITOR, EXPORT)
# ==========================================

@app.route('/approve/<int:user_id>')
@login_required
def approve_user(user_id):
    user_to_approve = User.query.get_or_404(user_id)
    is_authorized = False
    
    if current_user.role == 'hod' and user_to_approve.dept_code == current_user.dept_code:
        is_authorized = True
    elif current_user.role == 'mentor' and user_to_approve.dept_code == current_user.dept_code and user_to_approve.year_of_study == current_user.incharge_year:
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
    
    contest = Contest(name=name, link=link, platform=platform, date=date, 
                      dept_code=current_user.dept_code, created_by=current_user.id)
    db.session.add(contest)
    
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
    if current_user.role == 'student':
        return redirect(url_for('dashboard'))

    contest = Contest.query.get_or_404(contest_id)
    
    # Get assignments based on faculty scope
    query = Work.query.join(User).filter(Work.name == contest.name, Work.platform == contest.platform)
    
    if current_user.role in ['hod', 'mentor']:
        query = query.filter(User.dept_code == current_user.dept_code)
        if current_user.role == 'mentor':
            query = query.filter(User.year_of_study == current_user.incharge_year)
            
    assignments = query.all()

    # --- FACULTY AUTO-SYNC LOGIC ---
    updated_count = 0
    for work in assignments:
        if work.status == 'Pending':
            if check_contest_participation(work.user, work.name, work.platform):
                work.status = 'Submitted'
                updated_count += 1
                
    if updated_count > 0:
        db.session.commit()
        flash(f'Live Sync: Found {updated_count} new submissions!', 'success')

    return render_template('contest_monitor.html', contest=contest, assignments=assignments)

@app.route('/download_defaulters/<int:contest_id>')
@login_required
def download_defaulters(contest_id):
    if current_user.role == 'student':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))

    contest = Contest.query.get_or_404(contest_id)
    
    query = Work.query.join(User).filter(
        Work.name == contest.name, 
        Work.platform == contest.platform,
        Work.status == 'Pending'
    )
    
    if current_user.role in ['hod', 'mentor']:
        query = query.filter(User.dept_code == current_user.dept_code)
        if current_user.role == 'mentor':
            query = query.filter(User.year_of_study == current_user.incharge_year)
            
    defaulters = query.all()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Student Name', 'Email', 'Department', 'Year', 'Platform', 'Handle', 'Status'])
    
    for work in defaulters:
        u = work.user
        handle = u.lc_handle if contest.platform == 'LeetCode' else (u.cf_handle if contest.platform == 'Codeforces' else u.cc_handle)
        cw.writerow([u.name, u.email, u.dept_code, u.year_of_study, contest.platform, handle, 'Defaulter'])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=Defaulters_{contest.name.replace(' ', '_')}.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output

@app.route('/download_daily_defaulters/<platform>')
@login_required
def download_daily_defaulters(platform):
    if current_user.role == 'student':
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))

    # Get the requested date from the URL (defaults to today if none provided)
    target_date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    platform_name = "LeetCode" if platform.lower() == 'leetcode' else "Codeforces"

    # Filter students based on the viewer's faculty scope
    query = User.query.filter_by(role='student', is_approved=True)
    if current_user.role in ['hod', 'mentor']:
        query = query.filter(User.dept_code == current_user.dept_code)
        if current_user.role == 'mentor':
            query = query.filter(User.year_of_study == current_user.incharge_year)
            
    students = query.all()

    # Setup CSV Writer
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['Student Name', 'Email', 'Department', 'Year', 'Platform', 'Handle', 'Date', 'Problems Solved', 'Status'])

    # Scrape live data for each student to check their daily activity
    for s in students:
        stats = get_detailed_stats(s)
        p_stats = stats.get(platform_name, {})
        handle = s.lc_handle if platform_name == 'LeetCode' else s.cf_handle
        
        # If profile is missing or invalid
        if not handle or p_stats.get('error'):
            cw.writerow([s.name, s.email, s.dept_code, s.year_of_study, platform_name, "Not Linked/Error", target_date, 0, 'Defaulter'])
            continue
            
        # Find the solved count for the requested date
        history = p_stats.get('history', [])
        solved_count = 0
        
        if target_date == datetime.now().strftime('%Y-%m-%d'):
            solved_count = p_stats.get('today_count', 0)
        else:
            for day in history:
                if day['date'] == target_date:
                    solved_count = day['count']
                    break
        
        # If they solved 0 problems, they are a defaulter
        if solved_count == 0:
            cw.writerow([s.name, s.email, s.dept_code, s.year_of_study, platform_name, handle, target_date, solved_count, 'Defaulter'])

    # Output the CSV File
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={platform_name}_Daily_Defaulters_{target_date}.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)