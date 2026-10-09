"""
Seeds a working demo of Meridian General:
    admin  / Admin@123   (role=admin)
    doctor / Doctor@123  (role=doctor, Cardiology)
    staff  / Staff@123   (role=staff)

Plus departments, a couple more doctors, sample patients, and a few
scheduled appointments -- so the dashboard and public homepage aren't
empty on first run.

Usage: python seed.py
"""
from datetime import date, datetime, timedelta
from app import create_app
from app.models import db, User, Department, DoctorProfile, Patient, Appointment

app = create_app()

with app.app_context():

    # --- Departments ---------------------------------------------------
    dept_defs = [
        ("Cardiology", "Heart health, from checkups to complex procedures.", "🫀"),
        ("Pediatrics", "Care for infants, children, and teenagers.", "🧸"),
        ("Orthopedics", "Bones, joints, and everything that lets you move.", "🦴"),
        ("Dermatology", "Skin, hair, and nail conditions.", "🩹"),
    ]
    depts = {}
    for name, desc, icon in dept_defs:
        d = Department.query.filter_by(name=name).first()
        if not d:
            d = Department(name=name, description=desc, icon=icon)
            db.session.add(d)
            db.session.flush()
            print(f"[created] department: {name}")
        depts[name] = d
    db.session.commit()

    # --- Users + doctor profiles ----------------------------------------
    def ensure_user(username, password, role, full_name):
        u = User.query.filter_by(username=username).first()
        if u:
            u.is_active = True
            u.is_blocked = False
            u.blocked_reason = None
            u.blocked_at = None
            print(f"[skip] {username} already exists")
            return u
        u = User(username=username, role=role, full_name=full_name)
        u.set_password(password)
        db.session.add(u)
        db.session.flush()
        print(f"[created] {username} ({role})")
        return u

    admin = ensure_user("admin", "Admin@123", "admin", "Priya Deshmukh")
    doctor = ensure_user("doctor", "Doctor@123", "doctor", "Dr. Ananya Rao")
    staff = ensure_user("staff", "Staff@123", "staff", "Kabir Shaikh")
    doctor2 = ensure_user("dr_mehta", "Doctor@123", "doctor", "Dr. Rohan Mehta")
    db.session.commit()

    def ensure_profile(user, dept_name, specialization, qualification, years):
        if not DoctorProfile.query.filter_by(user_id=user.id).first():
            db.session.add(DoctorProfile(
                user_id=user.id, department_id=depts[dept_name].id,
                specialization=specialization, qualification=qualification,
                years_experience=years,
                bio=f"{specialization} at Meridian General, {dept_name} department.",
            ))
            print(f"[created] doctor profile for {user.username}")

    ensure_profile(doctor, "Cardiology", "Cardiologist", "MD, DM Cardiology", 11)
    ensure_profile(doctor2, "Pediatrics", "Pediatrician", "MD Pediatrics", 7)
    db.session.commit()

    # --- Sample patients --------------------------------------------------
    patient_defs = [
        ("Ravi Kulkarni", date(1985, 4, 12), "Male", "9876500001", "O+"),
        ("Sneha Patil", date(1993, 9, 2), "Female", "9876500002", "B+"),
        ("Arjun Nair", date(2015, 1, 20), "Male", "9876500003", "A+"),
    ]
    patients = {}
    for name, dob, gender, phone, blood in patient_defs:
        p = Patient.query.filter_by(name=name).first()
        if not p:
            p = Patient(name=name, date_of_birth=dob, gender=gender, phone=phone,
                        blood_group=blood, created_by=staff.id)
            db.session.add(p)
            db.session.flush()
            print(f"[created] patient: {name}")
        patients[name] = p
    db.session.commit()

    # --- Sample appointments ----------------------------------------------
    if Appointment.query.count() == 0:
        tomorrow = datetime.utcnow().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        db.session.add(Appointment(
            patient_id=patients["Ravi Kulkarni"].id, doctor_id=doctor.id,
            department_id=depts["Cardiology"].id, scheduled_at=tomorrow,
            reason="Routine cardiac checkup", created_by=staff.id,
        ))
        db.session.add(Appointment(
            patient_id=patients["Arjun Nair"].id, doctor_id=doctor2.id,
            department_id=depts["Pediatrics"].id, scheduled_at=tomorrow + timedelta(hours=2),
            reason="Annual pediatric visit", created_by=staff.id,
        ))
        db.session.commit()
        print("[created] sample appointments")

print("\nDemo credentials:")
print("  admin    -> admin / Admin@123")
print("  doctor   -> doctor / Doctor@123  (Cardiology)")
print("  doctor2  -> dr_mehta / Doctor@123  (Pediatrics)")
print("  staff    -> staff / Staff@123")
