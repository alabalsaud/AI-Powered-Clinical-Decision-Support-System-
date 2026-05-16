# AI-CDSS — Full Stack Setup Guide
## MacBook 2017 · VS Code · React + FastAPI + PostgreSQL

---

## OVERVIEW

```
Browser (React)  ←→  FastAPI (Python)  ←→  PostgreSQL
localhost:5173       localhost:8000         localhost:5432
```

---

## PART 1 — PostgreSQL Setup

### Install PostgreSQL (if not installed)
Download from: https://postgresapp.com  ← easiest on Mac
OR via Homebrew:
```bash
brew install postgresql@15
brew services start postgresql@15
```

### Create Database & User
Open Terminal and run:
```bash
psql -U postgres
```
Then paste this SQL:
```sql
CREATE USER cdss_user WITH PASSWORD 'cdss_password';
CREATE DATABASE cdss_db OWNER cdss_user;
GRANT ALL PRIVILEGES ON DATABASE cdss_db TO cdss_user;
\q
```
Or run the setup file directly:
```bash
psql -U postgres -f cdss-backend/setup_db.sql
```

---

## PART 2 — Backend Setup (FastAPI)

### Prerequisites
- Python 3.11 or 3.12  
  Check: `python3 --version`  
  Download: https://python.org

### Open VS Code Terminal in the backend folder
```bash
cd cdss-backend
```

### Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```
Your terminal prompt should show `(venv)` — do this every time you open a new terminal.

### Install dependencies
```bash
pip install -r requirements.txt
```

### Configure environment
The `.env` file is already set up with these defaults:
```
DATABASE_URL=postgresql://cdss_user:cdss_password@localhost:5432/cdss_db
SECRET_KEY=change-this-to-a-long-random-string-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=15
```
Change `SECRET_KEY` to a random string before using in production.

### Seed the database (run ONCE)
```bash
python seed_data.py
```
This creates all tables and inserts:
- 3 demo users (physician, nurse, admin)
- 12 medications with interactions
- 5 sample patients with allergies and conditions
- Sample diagnoses and prescriptions

### Start the backend server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Verify it works
Open browser → http://localhost:8000/docs
You should see the Swagger API documentation with all endpoints.

---

## PART 3 — Frontend Setup (React)

### Open a NEW Terminal tab, go to the frontend folder
```bash
cd cdss
```

### Install dependencies (first time only)
```bash
npm install
```

### Start the dev server
```bash
npm run dev
```

Open browser → http://localhost:5173

---

## LOGIN CREDENTIALS

| Role        | Email                       | Password        |
|-------------|-----------------------------|-----------------|
| Physician   | dr.alanoud@hospital.sa      | SecurePass123!  |
| Nurse       | nurse.reem@hospital.sa      | SecurePass123!  |
| Admin       | admin@hospital.sa           | AdminPass123!   |

---

## RUNNING BOTH SERVERS

You need **2 terminal tabs** open at the same time:

**Terminal 1 — Backend:**
```bash
cd cdss-backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd cdss
npm run dev
```

---

## PROJECT STRUCTURE

```
cdss-backend/                    ← FastAPI Backend
├── main.py                      ← App entry point
├── requirements.txt             ← Python packages
├── .env                         ← Database config
├── setup_db.sql                 ← PostgreSQL setup
├── seed_data.py                 ← Seeds demo data
└── app/
    ├── core/
    │   ├── config.py            ← Settings (pydantic-settings)
    │   └── security.py          ← JWT auth + password hashing
    ├── db/
    │   └── database.py          ← SQLAlchemy engine + session
    ├── models/
    │   └── models.py            ← All ORM models (12 tables)
    ├── schemas/
    │   └── schemas.py           ← Pydantic request/response models
    ├── services/
    │   ├── drug_safety.py       ← Drug-drug + drug-allergy checker
    │   └── audit.py             ← Audit log service
    └── api/routes/
        ├── auth.py              ← Login, register, JWT
        ├── patients.py          ← Patient CRUD
        ├── diagnoses.py         ← AI diagnosis save/confirm
        ├── prescriptions.py     ← Prescriptions + safety check
        ├── treatments.py        ← Treatment plans
        └── audit.py             ← Audit log retrieval

cdss/                            ← React Frontend
├── src/
│   ├── api.js                   ← All API calls to FastAPI
│   ├── App.jsx                  ← Root with routing + sidebar
│   ├── components/UI.jsx        ← Shared components
│   ├── data/mockData.js         ← Fallback data (offline mode)
│   ├── styles/global.css        ← Full design system
│   └── pages/
│       ├── LoginPage.jsx        ← Auth (FR10)
│       ├── Dashboard.jsx        ← Overview
│       ├── PatientManagement.jsx← CRUD (FR1)
│       ├── PatientDetail.jsx    ← Patient profile
│       ├── DiagnosisEngine.jsx  ← AI Diagnosis (FR3, FR8)
│       ├── TreatmentPlanning.jsx← Treatments (FR4)
│       ├── PrescriptionModule.jsx← Drug Safety (FR5, FR6, FR7)
│       └── OtherPages.jsx       ← Reports, Audit, Settings
```

---

## DATABASE TABLES

| Table              | Description                        |
|--------------------|------------------------------------|
| users              | Healthcare professionals + auth    |
| patients           | Patient demographics               |
| medical_histories  | Conditions per patient             |
| allergies          | Drug/food/env allergies            |
| clinical_notes     | NLP-processed notes                |
| diagnoses          | AI + physician diagnoses           |
| ai_analyses        | SHAP/LIME XAI data                 |
| treatment_plans    | Evidence-based treatment plans     |
| medications        | Drug reference table               |
| drug_interactions  | Drug-drug interaction pairs        |
| prescriptions      | Prescription records               |
| safety_checks      | Drug safety check results          |
| audit_logs         | Full tamper-proof audit trail      |

---

## API ENDPOINTS

| Method | Endpoint                            | Description              |
|--------|-------------------------------------|--------------------------|
| POST   | /api/v1/auth/register               | Register user            |
| POST   | /api/v1/auth/login                  | Login + get JWT token    |
| GET    | /api/v1/auth/me                     | Current user             |
| GET    | /api/v1/patients/                   | List patients            |
| POST   | /api/v1/patients/                   | Create patient           |
| GET    | /api/v1/patients/{id}               | Get patient detail       |
| PUT    | /api/v1/patients/{id}               | Update patient           |
| GET    | /api/v1/diagnoses/patient/{id}      | Patient diagnoses        |
| POST   | /api/v1/diagnoses/                  | Save AI diagnosis        |
| PUT    | /api/v1/diagnoses/{id}/confirm      | Confirm diagnosis        |
| POST   | /api/v1/prescriptions/safety-check  | Check drug safety        |
| POST   | /api/v1/prescriptions/              | Create prescription      |
| GET    | /api/v1/prescriptions/patient/{id}  | Patient prescriptions    |
| POST   | /api/v1/treatments/                 | Create treatment plan    |
| GET    | /api/v1/audit/                      | Audit logs               |

Full interactive docs: http://localhost:8000/docs

---

## TROUBLESHOOTING

**"Cannot connect to database"**
→ Make sure PostgreSQL is running: `brew services start postgresql@15`
→ Check your .env DATABASE_URL matches your PostgreSQL setup

**"Module not found"**
→ Make sure venv is active: `source venv/bin/activate`

**"CORS error" in browser**
→ Make sure backend is running on port 8000
→ Check ALLOWED_ORIGINS in .env includes http://localhost:5173

**Frontend shows "Backend offline"**
→ Start the FastAPI server first
→ The app still works with demo data (offline mode)

**Port already in use**
→ Backend: `uvicorn main:app --reload --port 8001`
→ Update ALLOWED_ORIGINS and api.js BASE URL accordingly
