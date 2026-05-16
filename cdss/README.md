# AI-Powered CDSS — Setup Guide (MacBook 2017 + VS Code)

## Prerequisites

You need Node.js installed. Open Terminal and check:
```
node -v
```
If not installed, go to https://nodejs.org and download the **LTS** version.

---

## Step-by-Step Setup

### 1. Open VS Code
Open VS Code. Then open the **integrated terminal**:
- Menu → Terminal → New Terminal  
- OR shortcut: `Ctrl + `` ` (backtick)

### 2. Navigate to this folder
In the terminal, go to where you saved this project:
```bash
cd ~/Desktop/cdss
```
*(adjust path if you saved it elsewhere)*

### 3. Install dependencies
```bash
npm install
```
This downloads React, Vite and all dependencies into a `node_modules` folder. Takes ~30 seconds.

### 4. Start the development server
```bash
npm run dev
```
You will see output like:
```
  VITE v5.x  ready in 400ms
  ➜  Local:   http://localhost:5173/
```

### 5. Open in browser
Go to: **http://localhost:5173**

---

## Default Login Credentials
- **Email:** dr.alanoud@hospital.sa  
- **Password:** SecurePass123!

Or register a new account with any email + password (min. 8 chars to login, min. 12 chars to register).

---

## Project Structure
```
cdss/
├── index.html              ← Entry HTML
├── package.json            ← Dependencies
├── vite.config.js          ← Vite config
└── src/
    ├── main.jsx            ← React entry point
    ├── App.jsx             ← Root app + routing + sidebar
    ├── styles/
    │   └── global.css      ← Full design system
    ├── data/
    │   └── mockData.js     ← Sample patients, diagnoses, prescriptions
    ├── components/
    │   └── UI.jsx          ← Shared components (Modal, Tabs, Badge, etc.)
    └── pages/
        ├── LoginPage.jsx          ← Auth with lockout (FR10)
        ├── Dashboard.jsx          ← Overview + stats + alerts
        ├── PatientManagement.jsx  ← Patient CRUD (FR1)
        ├── PatientDetail.jsx      ← Patient profile + timeline
        ├── DiagnosisEngine.jsx    ← AI diagnosis wizard (FR3, FR8)
        ├── TreatmentPlanning.jsx  ← Evidence-based treatments (FR4)
        ├── PrescriptionModule.jsx ← Drug safety checker (FR5, FR6, FR7)
        └── OtherPages.jsx         ← Reports, Audit Logs, Settings
```

---

## Features Implemented

| FR/NFR | Feature | Status |
|--------|---------|--------|
| FR1 | Patient Data Management (CRUD) | ✅ |
| FR2 | NLP Clinical Notes (UI) | ✅ |
| FR3 | AI Diagnostic Suggestions (RF+NN+BERT simulated) | ✅ |
| FR4 | Treatment Recommendations with guidelines | ✅ |
| FR5 | Drug-Drug Interaction Detection | ✅ |
| FR6 | Drug-Allergy Interaction Detection | ✅ |
| FR7 | Medication Recommendations | ✅ |
| FR8 | Explainable AI (XAI) with SHAP/LIME factors | ✅ |
| FR9 | Data Security (AES-256 noted, HIPAA badge) | ✅ |
| FR10 | Authentication with lockout (5 attempts) | ✅ |
| NFR4 | Usability — 3-click navigation | ✅ |
| NFR5 | Password complexity enforcement | ✅ |
| NFR12 | Audit Logs with full trail | ✅ |

---

## Stopping the Server
Press `Ctrl + C` in the terminal.

## Rebuild / Update
```bash
npm run build    # production build
npm run preview  # preview production build
```
