import unittest

try:
    from app import create_app
    from app.models import db, Department, DoctorProfile, Patient, PublicInquiry, User
    from app.hospital.routes import _INQUIRY_GUARD, _INQUIRY_LOCK
    from flask_jwt_extended import create_access_token
    IMPORT_OK = True
except Exception as exc:  # dependencies may not be installed in this archive build environment
    IMPORT_OK = False
    IMPORT_ERROR = exc


@unittest.skipUnless(IMPORT_OK, "Install requirements.txt before running integration tests")
class PublicSiteTests(unittest.TestCase):
    def setUp(self):
        with _INQUIRY_LOCK:
            _INQUIRY_GUARD.clear()
        app = create_app()
        app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
        self.app = app
        self.client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(Department(name="Cardiology", description="Heart care"))
            db.session.commit()

    def test_home_is_public(self):
        response = self.client.get("/")
        self.assertIn(response.status_code, (200, 304))

    def test_public_departments_are_read_only(self):
        response = self.client.get("/api/public/departments")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json[0]["name"], "Cardiology")

    def test_public_doctors_are_read_only_and_non_sensitive(self):
        response = self.client.get("/api/public/doctors")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, [])

    def test_appointment_doctor_options_use_active_user_ids(self):
        with self.app.app_context():
            admin = User(username="test-admin", role="admin", full_name="Test Admin")
            admin.set_password("test-password")
            staff = User(username="test-staff", role="staff", full_name="Test Staff")
            staff.set_password("test-password")
            doctor = User(username="test-doctor", role="doctor", full_name="Dr Test")
            doctor.set_password("test-password")
            doctor_without_profile = User(username="profileless-doctor", role="doctor", full_name="Dr Profileless")
            doctor_without_profile.set_password("test-password")
            inactive_doctor = User(username="inactive-doctor", role="doctor", full_name="Inactive Doctor", is_active=False)
            inactive_doctor.set_password("test-password")
            blocked_doctor = User(username="blocked-doctor", role="doctor", full_name="Blocked Doctor", is_blocked=True)
            blocked_doctor.set_password("test-password")
            db.session.add_all([admin, staff, doctor, doctor_without_profile, inactive_doctor, blocked_doctor])
            db.session.flush()
            department = Department.query.filter_by(name="Cardiology").one()
            db.session.add(DoctorProfile(user_id=doctor.id, department_id=department.id))
            patient = Patient(name="Test Patient", created_by=staff.id)
            db.session.add(patient)
            db.session.commit()
            token = create_access_token(identity=str(admin.id), additional_claims={"role": "admin"})
            patient_id = patient.id
            doctor_user_id = doctor.id
            department_id = department.id
            profile_id = DoctorProfile.query.filter_by(user_id=doctor.id).one().id
            doctor_without_profile_id = doctor_without_profile.id
            inactive_doctor_id = inactive_doctor.id
            blocked_doctor_id = blocked_doctor.id

        headers = {"Authorization": f"Bearer {token}"}
        response = self.client.get("/api/doctors", headers=headers)
        self.assertEqual(response.status_code, 200)
        options = {item["id"]: item for item in response.json}
        self.assertEqual(options[doctor_user_id]["full_name"], "Dr Test")
        self.assertIn(doctor_without_profile_id, options)
        self.assertNotIn(inactive_doctor_id, options)
        self.assertNotIn(blocked_doctor_id, options)
        self.assertNotEqual(profile_id, doctor_user_id)

        appointment = self.client.post("/api/appointments", headers=headers, json={
            "patient_id": patient_id,
            "doctor_id": options[doctor_user_id]["id"],
            "department_id": department_id,
            "scheduled_at": "2026-10-09T10:00:00",
        })
        self.assertEqual(appointment.status_code, 201)
        self.assertEqual(appointment.json["doctor_id"], doctor_user_id)
        self.assertEqual(appointment.json["department_name"], "Cardiology")

        listed = self.client.get("/api/appointments", headers=headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json[0]["department_name"], "Cardiology")

    def test_inquiry_requires_all_fields(self):
        response = self.client.post("/api/public/inquiries", json={"name": "A"})
        self.assertEqual(response.status_code, 400)

    def test_inquiry_rejects_unknown_sensitive_fields(self):
        payload = {
            "name": "Asha Patient", "email": "asha@example.com", "phone": "+919876543210",
            "department": "Cardiology", "message": "I would like to ask about an appointment.",
            "diagnosis": "secret"
        }
        response = self.client.post("/api/public/inquiries", json=payload)
        self.assertEqual(response.status_code, 400)

    def test_inquiry_validates_email_and_phone(self):
        base = {"name": "Asha Patient", "department": "Cardiology", "message": "Appointment enquiry"}
        bad_email = self.client.post("/api/public/inquiries", json={**base, "email": "bad", "phone": "+919876543210"})
        self.assertEqual(bad_email.status_code, 400)
        bad_phone = self.client.post("/api/public/inquiries", json={**base, "email": "asha@example.com", "phone": "abc"})
        self.assertEqual(bad_phone.status_code, 400)

    def test_valid_inquiry_is_saved_without_clinical_fields(self):
        payload = {"name": "Asha Patient", "email": "asha@example.com", "phone": "+919876543210", "department": "Cardiology", "message": "Please call me about a consultation."}
        response = self.client.post("/api/public/inquiries", json=payload)
        self.assertEqual(response.status_code, 201)
        with self.app.app_context():
            inquiry = PublicInquiry.query.one()
            self.assertEqual(inquiry.department, "Cardiology")
            self.assertFalse(hasattr(inquiry, "diagnosis"))


if __name__ == "__main__":
    unittest.main()
