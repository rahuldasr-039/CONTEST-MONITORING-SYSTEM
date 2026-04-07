from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

# Initialize Database
db = SQLAlchemy()

# ==========================================
# 1. USER MODEL (Handles Students, Mentors, HODs, Admin)
# ==========================================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    # --- Authentication Fields ---
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    
    # --- Role & Hierarchy ---
    role = db.Column(db.String(20), nullable=False)       # 'student', 'mentor', 'hod', 'incharge'
    dept_code = db.Column(db.String(20), nullable=False)  # e.g., 'CSE', 'ECE'
    is_approved = db.Column(db.Boolean, default=False)    # Must be approved by superior
    
    # --- Student Specific ---
    year_of_study = db.Column(db.Integer, nullable=True)  # 1, 2, 3, 4
    
    # --- Mentor Specific ---
    incharge_year = db.Column(db.Integer, nullable=True)  # Which year they manage
    
    # --- Platform Handles (For Scrapers) ---
    cf_handle = db.Column(db.String(50), nullable=True)   # Codeforces
    lc_handle = db.Column(db.String(50), nullable=True)   # LeetCode
    cc_handle = db.Column(db.String(50), nullable=True)   # CodeChef

    def __repr__(self):
        return f'<User {self.name} - {self.role}>'


# ==========================================
# 2. CONTEST MODEL (Assignments)
# ==========================================
class Contest(db.Model):
    __tablename__ = 'contests'

    id = db.Column(db.Integer, primary_key=True)
    
    # --- Contest Details ---
    name = db.Column(db.String(100), nullable=False)      # e.g., "Weekly Contest 350"
    platform = db.Column(db.String(50), nullable=False)   # "LeetCode" or "Codeforces"
    
    # --- NEW: The Assignment Link ---
    link = db.Column(db.String(200), nullable=False)      # URL to the contest
    
    # --- Logistics ---
    date = db.Column(db.String(20), nullable=False)       # Due Date (YYYY-MM-DD)
    dept_code = db.Column(db.String(20), nullable=False)  # Assigned to which Dept?
    
    def __repr__(self):
        return f'<Contest {self.name}>'