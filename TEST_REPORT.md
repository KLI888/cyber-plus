# Cyber-Pulse 2.5 — Regression & Public Website Test Report

## Scope
Tested the React + Flask source tree for authentication, RBAC, role-specific routing, clinical ownership, anomaly behavior, public entry points, data integrity, and syntax/build readiness.

## Automated checks completed

| ID | Test | Result |
|---|---|---|
| T01 | Python compilation of all application modules | PASS |
| T02 | React JSX parsing/transpilation with TypeScript compiler | PASS |
| T03 | Admin blueprint route RBAC coverage | PASS |
| T04 | Public `/` route exists | PASS |
| T05 | `/login` no longer blindly redirects on stale/expired token | PASS |
| T06 | `/auth/me` current-session endpoint exists | PASS |
| T07 | Server revalidates current database role against JWT role | PASS |
| T08 | Inactive/blocked accounts rejected by protected routes | PASS |
| T09 | Public self-registration remains disabled | PASS |
| T10 | Admin-only user provisioning preserved | PASS |
| T11 | Admin cannot block own account | PASS |
| T12 | Admin cannot delete/deactivate own account | PASS |
| T13 | User deactivation revokes existing sessions | PASS |
| T14 | User role change revokes existing sessions | PASS |
| T15 | Doctor appointment creation restricted to self | PASS |
| T16 | Doctor appointment updates restricted to own queue | PASS |
| T17 | Appointment doctor must be active and have doctor role | PASS |
| T18 | Medical record doctor ownership validated | PASS |
| T19 | Medical record appointment/patient/doctor relationship validated | PASS |
| T20 | Medical record visit date is parsed and persisted | PASS |
| T21 | Department rename collision handled | PASS |
| T22 | ML scoring path contains no automatic mitigation call | PASS |
| T23 | Legitimate synthetic behavior: 942/1000 normal, 58/1000 suspicious, 0 critical | PASS |
| T24 | Extreme synthetic attack pattern classified critical | PASS |
| T25 | SQLite demo data/schema sanity | PASS |

## Model verification

The bundled Isolation Forest/scaler was retrained with the declared scikit-learn 1.8.x range. The normal sample scored `0.151` / `normal`; the extreme attack sample scored `-0.176` / `critical`. No model-version warning occurred during verification.

## Environment limitation

The execution sandbox has no package-registry/network access. Therefore `pip install -r requirements.txt` and `npm install` could not download dependencies, so a live Flask HTTP test server and a production Vite bundle could not be executed here. The source was still syntax-checked, the existing SQLite database was inspected, the ML artifacts were executed directly, and the frontend JSX was parsed successfully.

## Recommended local release test

```bash
pip install -r requirements.txt
python seed.py
cd frontend
npm install
npm run build
cd ..
python run.py
```

Then manually verify: admin login, doctor login, staff login, admin-only users/security screens, doctor-only records, staff denial of records, account block/unblock, logout, expired token behavior, patient creation, appointment creation/completion, record creation, and the controlled security simulation.

## Public patient website checks added

| ID | Test | Result |
|---|---|---|
| P01 | Public `/` landing page remains unauthenticated | SOURCE PASS |
| P02 | Public departments endpoint returns non-sensitive department data | SOURCE PASS |
| P03 | Public doctors endpoint exposes only clinical-profile fields | SOURCE PASS |
| P04 | Public enquiry endpoint accepts only allow-listed non-clinical fields | SOURCE PASS |
| P05 | Enquiry requires all five fields | SOURCE PASS |
| P06 | Email format and phone character validation enforced server-side | SOURCE PASS |
| P07 | Field length limits enforced server-side | SOURCE PASS |
| P08 | Unknown fields such as diagnosis/prescription rejected | SOURCE PASS |
| P09 | Department must exist before enquiry is stored | SOURCE PASS |
| P10 | Public enquiry rate limited to four requests per source per 15 minutes | SOURCE PASS |
| P11 | Staff sign-in remains separate from public site | SOURCE PASS |
| P12 | Public site contains no links to authenticated clinical data | SOURCE PASS |
| P13 | Public controls and form fields are documented in executable/manual checklist | SOURCE PASS |

The seven public API integration tests are included in `tests/test_public_site.py`. They were discovered successfully but skipped in this build environment because Flask dependencies are not installed. `PUBLIC_SITE_TEST_CHECKLIST.md` contains the complete browser-level acceptance checklist.
