# Cyber-Pulse 2.5 — Public Website Test Checklist

## Public navigation
- [ ] Logo returns to the top of the page.
- [ ] Care scrolls to the care section.
- [ ] Specialists scrolls to specialist section.
- [ ] About scrolls to the hospital/security explanation.
- [ ] Contact scrolls to the enquiry form.
- [ ] Staff sign in opens `/login` and never exposes internal data.
- [ ] Request a visit scrolls to the enquiry form.
- [ ] Explore our care scrolls to the care section.
- [ ] Footer links work on desktop and mobile.

## Public content
- [ ] Departments load from the public API.
- [ ] Specialist cards load from the public API.
- [ ] Empty department/doctor data does not crash the page.
- [ ] No patient records, user accounts, JWTs, activity logs, or clinical notes are included in public API responses.

## Enquiry form — valid cases
- [ ] Valid name, email, phone, department and message submits successfully.
- [ ] Success state clears the form.
- [ ] Submit button disables while the request is in progress.

## Enquiry form — invalid cases
- [ ] Empty required fields are rejected by browser validation.
- [ ] Invalid email is rejected by browser and server validation.
- [ ] Invalid phone characters are rejected by server validation.
- [ ] Oversized name/email/phone/department/message are rejected by server validation.
- [ ] Invalid department is rejected by server validation.
- [ ] Extra fields such as diagnosis/prescription are rejected.
- [ ] More than four requests from one source within 15 minutes are rate-limited.

## Security boundaries
- [ ] `/` is public.
- [ ] `/api/public/departments` is public GET only.
- [ ] `/api/public/doctors` is public GET only.
- [ ] `/api/public/inquiries` is public POST only.
- [ ] No public endpoint accepts an Authorization token as a substitute for validation.
- [ ] `/dashboard` still requires authentication.
- [ ] `/users`, `/security`, `/alerts`, `/activity` remain admin-only.
- [ ] Doctor and staff cannot reach admin screens by typing URLs directly.

## Local integration run

```bash
pip install -r requirements.txt
python -m unittest tests.test_public_site -v
cd frontend
npm install
npm run build
cd ..
python run.py
```
