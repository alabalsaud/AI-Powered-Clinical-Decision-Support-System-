export const PATIENTS = [
  {
    id: 'PT-1001', name: 'Hayfa Almineefi', age: 45, gender: 'Female',
    dob: '1979-03-12', weight: 68, height: 162, bloodType: 'A+',
    phone: '0501234567', mrn: 'MRN-00451', lastVisit: 'Today', status: 'Active',
    allergies: ['Penicillin', 'Sulfa'],
    conditions: ['Type 2 Diabetes', 'Hypertension'],
    medications: ['Metformin 500mg', 'Lisinopril 10mg'],
  },
  {
    id: 'PT-1002', name: 'Loulwah Ababtain', age: 28, gender: 'Female',
    dob: '1996-07-24', weight: 55, height: 158, bloodType: 'O+',
    phone: '0512345678', mrn: 'MRN-00452', lastVisit: '2 days ago', status: 'Active',
    allergies: ['Aspirin'],
    conditions: ['Asthma'],
    medications: ['Salbutamol Inhaler 100mcg'],
  },
  {
    id: 'PT-1003', name: 'Luluh Almousa', age: 35, gender: 'Female',
    dob: '1989-11-03', weight: 62, height: 165, bloodType: 'B-',
    phone: '0523456789', mrn: 'MRN-00453', lastVisit: '1 week ago', status: 'Active',
    allergies: [],
    conditions: [],
    medications: [],
  },
  {
    id: 'PT-1004', name: 'Meshael Alissa', age: 52, gender: 'Female',
    dob: '1972-05-18', weight: 74, height: 160, bloodType: 'AB+',
    phone: '0534567890', mrn: 'MRN-00454', lastVisit: '3 days ago', status: 'Active',
    allergies: ['NSAIDs'],
    conditions: ['Hypothyroidism', 'Osteoporosis'],
    medications: ['Levothyroxine 50mcg', 'Calcium+D3'],
  },
  {
    id: 'PT-1005', name: 'Ahmed Al-Rashid', age: 45, gender: 'Male',
    dob: '1979-02-14', weight: 85, height: 175, bloodType: 'A-',
    phone: '0545678901', mrn: 'MRN-00455', lastVisit: '5 days ago', status: 'Active',
    allergies: ['Penicillin'],
    conditions: ['Type 2 Diabetes', 'CKD Stage II', 'Hypertension'],
    medications: ['Metformin 500mg', 'Amlodipine 5mg', 'Aspirin 81mg'],
  },
];

export const DIAGNOSES = [
  { id: 'DX-001', patientId: 'PT-1001', condition: 'Type 2 Diabetes Mellitus', icd: 'E11.9', confidence: 92, date: '2025-10-01', status: 'Confirmed', source: 'AI+Physician' },
  { id: 'DX-002', patientId: 'PT-1001', condition: 'Essential Hypertension',   icd: 'I10',   confidence: 88, date: '2025-08-15', status: 'Confirmed', source: 'Physician'     },
  { id: 'DX-003', patientId: 'PT-1002', condition: 'Bronchial Asthma',         icd: 'J45.9', confidence: 95, date: '2025-09-20', status: 'Confirmed', source: 'AI+Physician' },
  { id: 'DX-004', patientId: 'PT-1004', condition: 'Hypothyroidism',           icd: 'E03.9', confidence: 91, date: '2025-07-10', status: 'Confirmed', source: 'Physician'     },
  { id: 'DX-005', patientId: 'PT-1005', condition: 'Acute Coronary Syndrome',  icd: 'I24.9', confidence: 78, date: '2025-10-05', status: 'Under Review', source: 'AI'         },
];

export const PRESCRIPTIONS = [
  { id: 'RX-001', patientId: 'PT-1001', drug: 'Metformin 500mg',      dose: '500mg', freq: 'Twice daily', duration: 'Ongoing', status: 'Active', date: '2025-10-01', prescriber: 'Dr. Alanoud Alsaud', safety: 'Safe'    },
  { id: 'RX-002', patientId: 'PT-1001', drug: 'Lisinopril 10mg',      dose: '10mg',  freq: 'Once daily',  duration: 'Ongoing', status: 'Active', date: '2025-08-15', prescriber: 'Dr. Alanoud Alsaud', safety: 'Warning' },
  { id: 'RX-003', patientId: 'PT-1002', drug: 'Salbutamol 100mcg',    dose: '2 puffs', freq: 'As needed', duration: 'Ongoing', status: 'Active', date: '2025-09-20', prescriber: 'Dr. Alanoud Alsaud', safety: 'Safe'    },
];

export const DRUG_DB = [
  { id: 'D001', name: 'Metformin 500mg',    class: 'Biguanide',            indication: 'Type 2 Diabetes',          contraindications: ['CKD Stage IV-V', 'Liver disease'],   interactions: ['Alcohol', 'Contrast agents'] },
  { id: 'D002', name: 'Lisinopril 10mg',    class: 'ACE Inhibitor',        indication: 'Hypertension, Heart failure', contraindications: ['Pregnancy', 'Angioedema history'], interactions: ['NSAIDs', 'Potassium supplements'] },
  { id: 'D003', name: 'Amoxicillin 500mg',  class: 'Penicillin antibiotic',indication: 'Bacterial infections',     contraindications: ['Penicillin allergy'],                interactions: ['Warfarin', 'Methotrexate'] },
  { id: 'D004', name: 'Azithromycin 500mg', class: 'Macrolide antibiotic', indication: 'Bacterial infections',     contraindications: ['Liver disease', 'QT prolongation'],  interactions: ['Warfarin', 'QT-prolonging drugs'] },
  { id: 'D005', name: 'Atorvastatin 20mg',  class: 'Statin',               indication: 'Hyperlipidemia',           contraindications: ['Active liver disease', 'Pregnancy'],  interactions: ['Cyclosporine', 'Fibrates'] },
  { id: 'D006', name: 'Aspirin 81mg',       class: 'NSAID / Antiplatelet', indication: 'CVD prevention',           contraindications: ['Peptic ulcer', 'Aspirin allergy'],    interactions: ['Warfarin', 'Other NSAIDs'] },
  { id: 'D007', name: 'Empagliflozin 10mg', class: 'SGLT2 Inhibitor',      indication: 'Type 2 Diabetes, HF',     contraindications: ['eGFR <30', 'DKA'],                    interactions: ['Diuretics', 'Insulin'] },
  { id: 'D008', name: 'Levothyroxine 50mcg',class: 'Thyroid hormone',      indication: 'Hypothyroidism',           contraindications: ['Thyrotoxicosis', 'Adrenal insufficiency'], interactions: ['Calcium', 'Iron supplements'] },
];

export const AUDIT_LOGS = [
  { id: 1, user: 'Dr. Alanoud Alsaud', action: 'Login',              time: '10:24 AM', detail: 'Successful login from 192.168.1.5',                    type: 'auth'         },
  { id: 2, user: 'Dr. Alanoud Alsaud', action: 'Viewed Patient',    time: '10:26 AM', detail: 'Accessed PT-1001 (Hayfa Almineefi)',                    type: 'data'         },
  { id: 3, user: 'Dr. Alanoud Alsaud', action: 'AI Diagnosis',      time: '10:30 AM', detail: 'Generated diagnosis for PT-1001 — T2DM 92%',            type: 'clinical'     },
  { id: 4, user: 'Dr. Alanoud Alsaud', action: 'Prescription',      time: '10:35 AM', detail: 'Prescribed Metformin 500mg for PT-1001',                type: 'prescription' },
  { id: 5, user: 'Nurse Reem',         action: 'Patient Updated',   time: '11:02 AM', detail: 'Updated vitals for PT-1002',                            type: 'data'         },
  { id: 6, user: 'Dr. Alanoud Alsaud', action: 'Drug Safety Check', time: '11:15 AM', detail: 'Penicillin allergy flagged — Amoxicillin blocked',      type: 'prescription' },
  { id: 7, user: 'Dr. Alanoud Alsaud', action: 'Report Generated',  time: '11:40 AM', detail: 'Full Clinical Report exported for PT-1001',             type: 'clinical'     },
];
