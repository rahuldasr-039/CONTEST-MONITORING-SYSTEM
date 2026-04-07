from app import app, db, User
from werkzeug.security import generate_password_hash

# Create a fresh database context
with app.app_context():
    # 1. Drop all existing tables (CLEAN SLATE)
    db.drop_all()
    print("🗑️  Old database deleted.")

    # 2. Create new tables
    db.create_all()
    print("✅ New database created.")

    # 3. Create a DEFAULT HOD USER (so you can login)
    admin_password = generate_password_hash('admin123', method='pbkdf2:sha256')
    
    admin = User(
        name="System Admin",
        email="admin@college.edu",
        password=admin_password,
        role="hod",           # Role is HOD
        dept_code="CSE",      # Default Dept
        is_approved=True      # Auto-approved!
    )

    db.session.add(admin)
    db.session.commit()
    
    print("🚀 Admin User Created!")
    print("--------------------------------")
    print("📧 Email:    admin@college.edu")
    print("🔑 Password: admin123")
    print("--------------------------------")