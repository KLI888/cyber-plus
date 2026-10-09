# Cyber-Pulse 2.4 — React + Flask Hardened Build

Cyber-Pulse is a healthcare security and operations platform built around Flask, JWT/RBAC and an Isolation Forest anomaly-detection pipeline.

## Architecture

- **Backend:** Flask + SQLAlchemy + JWT + RBAC + ML anomaly detection
- **Frontend:** React + Vite + React Router + Recharts + Lucide
- **UI:** handcrafted enterprise healthcare/security design system; no UI framework dependency
- **Database:** existing SQLite database remains compatible; `DATABASE_URL` can point to PostgreSQL/MySQL
- **Security:** short-lived access tokens, session revocation, account blocking, security headers, login rate guard, least-privilege clinical endpoints, admin-only account provisioning, role-aware dashboards, non-destructive anomaly detection, and server-side role revalidation


## Run the backend

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## Run the React UI in development

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` to `http://localhost:5000`.

## Build the React UI for Flask

```bash
cd frontend
npm run build
```

The build is written to `app/static/dist`, and Flask serves the SPA for all non-API routes.

## Security notes

Set production secrets through environment variables:

- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `DATABASE_URL`

For local development, an omitted `JWT_SECRET_KEY` is generated randomly at startup; restarting Flask invalidates existing login tokens. Configure a stable secret of at least 32 bytes in production.

Serve behind HTTPS in production. The ML detector is non-destructive: suspicious/critical activity creates an admin-review event; only an explicit administrator action blocks an account. The simulation is also non-destructive. Public login is available to demo accounts, while new accounts can only be provisioned by an administrator.

### Demo accounts

- Admin: `admin` / `Admin@123`
- Doctor: `doctor` / `Doctor@123`
- Staff: `staff` / `Staff@123`

Change seeded credentials before any real deployment.

## Public Patient Website

`/` is now the public patient-facing hospital landing page. It is intentionally separate from the authenticated operations console at `/dashboard`.

The public site exposes only non-sensitive hospital information through:
- `GET /api/public/departments`
- `GET /api/public/doctors`
- `POST /api/public/inquiries`

The enquiry endpoint accepts only name, email, phone, department and a general message. It rejects clinical fields, validates input server-side, enforces field length limits, checks the department against the database, and rate-limits public submissions.

Do not put diagnoses, prescriptions, medical record numbers, or other sensitive clinical information into the public enquiry form.
