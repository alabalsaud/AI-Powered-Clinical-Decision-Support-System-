"""
SQLAlchemy ORM models.
Schema matches the ERD in the SRS document (Section 3).
All tables are in 3NF with optimistic locking (version column).
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Integer, String, Float, Boolean, Text,
    DateTime, ForeignKey, JSON, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.core.pii_crypto import EncryptedString
import enum


# ─── Enums ────────────────────────────────────────────────
class UserRole(str, enum.Enum):
    physician      = "physician"
    nurse          = "nurse"
    pharmacist     = "pharmacist"
    administrator  = "administrator"


class Gender(str, enum.Enum):
    male   = "Male"
    female = "Female"
    other  = "Other"


class AllergySeverity(str, enum.Enum):
    mild     = "Mild"
    moderate = "Moderate"
    severe   = "Severe"


class InteractionSeverity(str, enum.Enum):
    minor            = "Minor"
    moderate         = "Moderate"
    major            = "Major"
    contraindicated  = "Contraindicated"


class PrescriptionStatus(str, enum.Enum):
    pending   = "Pending"
    active    = "Active"
    completed = "Completed"
    cancelled = "Cancelled"


class DiagnosisStatus(str, enum.Enum):
    suggested    = "Suggested"
    confirmed    = "Confirmed"
    under_review = "Under Review"
    rejected     = "Rejected"


class SafetyResult(str, enum.Enum):
    safe     = "Safe"
    warning  = "Warning"
    critical = "Critical"
    blocked  = "Blocked"


# ─── USER ─────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str]        = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str]           = mapped_column(String(200), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str]       = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole]       = mapped_column(SAEnum(UserRole), default=UserRole.physician)
    license_number: Mapped[Optional[str]] = mapped_column(String(100))
    profile_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool]      = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    account_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int]         = mapped_column(Integer, default=1)   # optimistic locking

    # Relationships
    clinical_notes: Mapped[List["ClinicalNote"]]  = relationship("ClinicalNote",  back_populates="author")
    diagnoses:      Mapped[List["Diagnosis"]]      = relationship("Diagnosis",      back_populates="physician")
    prescriptions:  Mapped[List["Prescription"]]   = relationship("Prescription",   back_populates="prescriber")
    audit_logs:     Mapped[List["AuditLog"]]        = relationship("AuditLog",        back_populates="user")


# ─── PATIENT ──────────────────────────────────────────────
class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    mrn: Mapped[str]             = mapped_column(String(50), unique=True, nullable=False, index=True)
    first_name: Mapped[str]      = mapped_column(EncryptedString(512), nullable=False)
    last_name: Mapped[str]       = mapped_column(EncryptedString(512), nullable=False)
    date_of_birth: Mapped[str]   = mapped_column(EncryptedString(256), nullable=False)
    gender: Mapped[Gender]       = mapped_column(SAEnum(Gender))
    weight: Mapped[Optional[float]] = mapped_column(Float)
    height: Mapped[Optional[float]] = mapped_column(Float)
    blood_type: Mapped[Optional[str]] = mapped_column(String(5))
    phone: Mapped[Optional[str]] = mapped_column(EncryptedString(256), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(EncryptedString(512), nullable=True)
    is_active: Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int]         = mapped_column(Integer, default=1)

    # Relationships
    medical_histories: Mapped[List["MedicalHistory"]] = relationship("MedicalHistory", back_populates="patient", cascade="all, delete-orphan")
    allergies:         Mapped[List["Allergy"]]         = relationship("Allergy",         back_populates="patient", cascade="all, delete-orphan")
    clinical_notes:    Mapped[List["ClinicalNote"]]    = relationship("ClinicalNote",    back_populates="patient", cascade="all, delete-orphan")
    diagnoses:         Mapped[List["Diagnosis"]]       = relationship("Diagnosis",       back_populates="patient", cascade="all, delete-orphan")
    prescriptions:     Mapped[List["Prescription"]]    = relationship("Prescription",    back_populates="patient", cascade="all, delete-orphan")
    treatment_plans:   Mapped[List["TreatmentPlan"]]   = relationship("TreatmentPlan",   back_populates="patient", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


# ─── MEDICAL HISTORY ──────────────────────────────────────
class MedicalHistory(Base):
    __tablename__ = "medical_histories"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int]      = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    condition: Mapped[str]       = mapped_column(String(300), nullable=False)
    icd_code: Mapped[Optional[str]] = mapped_column(String(20))
    diagnosed_date: Mapped[Optional[str]] = mapped_column(String(20))
    is_active: Mapped[bool]      = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="medical_histories")


# ─── ALLERGY ──────────────────────────────────────────────
class Allergy(Base):
    __tablename__ = "allergies"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int]      = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    allergen: Mapped[str]        = mapped_column(String(200), nullable=False)
    allergy_type: Mapped[str]    = mapped_column(String(50))   # Drug / Food / Environmental
    severity: Mapped[AllergySeverity] = mapped_column(SAEnum(AllergySeverity), default=AllergySeverity.moderate)
    reaction: Mapped[Optional[str]]   = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="allergies")


# ─── CLINICAL NOTE ────────────────────────────────────────
class ClinicalNote(Base):
    __tablename__ = "clinical_notes"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int]      = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[int]       = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    note_text: Mapped[str]       = mapped_column(Text, nullable=False)
    symptoms: Mapped[Optional[str]]       = mapped_column(Text)   # comma-separated extracted symptoms
    observations: Mapped[Optional[str]]   = mapped_column(Text)
    extracted_entities: Mapped[Optional[dict]] = mapped_column(JSON)  # NLP output
    note_date: Mapped[datetime]  = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    patient: Mapped["Patient"] = relationship("Patient", back_populates="clinical_notes")
    author:  Mapped["User"]    = relationship("User",    back_populates="clinical_notes")


# ─── DIAGNOSIS ────────────────────────────────────────────
class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int]      = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    physician_id: Mapped[int]    = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    diagnosis_code: Mapped[Optional[str]]  = mapped_column(String(20))   # ICD-10
    diagnosis_name: Mapped[str]  = mapped_column(String(300), nullable=False)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[DiagnosisStatus] = mapped_column(SAEnum(DiagnosisStatus), default=DiagnosisStatus.suggested)
    source: Mapped[str]          = mapped_column(String(50), default="AI")  # AI / Physician / AI+Physician
    is_confirmed: Mapped[bool]   = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    diagnosed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime]   = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int]           = mapped_column(Integer, default=1)

    patient:    Mapped["Patient"]   = relationship("Patient",   back_populates="diagnoses")
    physician:  Mapped["User"]      = relationship("User",      back_populates="diagnoses")
    ai_analysis: Mapped[Optional["AIAnalysis"]] = relationship("AIAnalysis", back_populates="diagnosis", uselist=False, cascade="all, delete-orphan")
    treatment_plans: Mapped[List["TreatmentPlan"]] = relationship("TreatmentPlan", back_populates="diagnosis")


# ─── AI ANALYSIS ──────────────────────────────────────────
class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int]               = mapped_column(Integer, primary_key=True, index=True)
    diagnosis_id: Mapped[int]     = mapped_column(Integer, ForeignKey("diagnoses.id", ondelete="CASCADE"), unique=True, nullable=False)
    model_version: Mapped[str]    = mapped_column(String(50), default="ensemble-v1")
    confidence_score: Mapped[float] = mapped_column(Float)
    shap_values: Mapped[Optional[dict]] = mapped_column(JSON)   # SHAP feature importances
    lime_values: Mapped[Optional[dict]] = mapped_column(JSON)   # LIME explanations
    feature_importance: Mapped[Optional[dict]] = mapped_column(JSON)
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    all_suggestions: Mapped[Optional[dict]] = mapped_column(JSON)  # full ranked list
    analysed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    diagnosis: Mapped["Diagnosis"] = relationship("Diagnosis", back_populates="ai_analysis")


# ─── TREATMENT PLAN ───────────────────────────────────────
class TreatmentPlan(Base):
    __tablename__ = "treatment_plans"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int]      = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    diagnosis_id: Mapped[int]    = mapped_column(Integer, ForeignKey("diagnoses.id"), nullable=False)
    title: Mapped[str]           = mapped_column(String(300), nullable=False)
    treatment_description: Mapped[str] = mapped_column(Text)
    medications: Mapped[Optional[dict]] = mapped_column(JSON)    # list of medication objects
    lifestyle: Mapped[Optional[dict]]   = mapped_column(JSON)
    monitoring: Mapped[Optional[dict]]  = mapped_column(JSON)
    references: Mapped[Optional[dict]]  = mapped_column(JSON)    # clinical guideline refs
    is_active: Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    patient:   Mapped["Patient"]   = relationship("Patient",   back_populates="treatment_plans")
    diagnosis: Mapped["Diagnosis"] = relationship("Diagnosis", back_populates="treatment_plans")
    prescriptions: Mapped[List["Prescription"]] = relationship("Prescription", back_populates="treatment_plan")


# ─── MEDICATION ───────────────────────────────────────────
class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    generic_name: Mapped[str]    = mapped_column(String(200), nullable=False, index=True)
    brand_names: Mapped[Optional[str]] = mapped_column(Text)     # comma-separated
    drug_class: Mapped[Optional[str]]  = mapped_column(String(100))
    indication: Mapped[Optional[str]]  = mapped_column(Text)
    contraindications: Mapped[Optional[dict]] = mapped_column(JSON)
    common_interactions: Mapped[Optional[dict]] = mapped_column(JSON)
    max_daily_dose: Mapped[Optional[str]] = mapped_column(String(50))
    is_active: Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    prescriptions: Mapped[List["Prescription"]] = relationship("Prescription", back_populates="medication")


# ─── DRUG INTERACTION ─────────────────────────────────────
class DrugInteraction(Base):
    __tablename__ = "drug_interactions"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    medication_id_1: Mapped[int] = mapped_column(Integer, ForeignKey("medications.id"), nullable=False)
    medication_id_2: Mapped[int] = mapped_column(Integer, ForeignKey("medications.id"), nullable=False)
    severity: Mapped[InteractionSeverity] = mapped_column(SAEnum(InteractionSeverity))
    description: Mapped[str]     = mapped_column(Text)
    clinical_effect: Mapped[Optional[str]] = mapped_column(Text)
    management: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ─── PRESCRIPTION ─────────────────────────────────────────
class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int]      = mapped_column(Integer, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    prescriber_id: Mapped[int]   = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    medication_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medications.id"))
    treatment_plan_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("treatment_plans.id"))
    drug_name: Mapped[str]       = mapped_column(String(200), nullable=False)   # free text fallback
    dose: Mapped[str]            = mapped_column(String(100), nullable=False)
    frequency: Mapped[str]       = mapped_column(String(100))
    route: Mapped[str]           = mapped_column(String(50), default="Oral")
    duration: Mapped[str]        = mapped_column(String(100))
    special_instructions: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[PrescriptionStatus] = mapped_column(SAEnum(PrescriptionStatus), default=PrescriptionStatus.active)
    prescribed_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    version: Mapped[int]         = mapped_column(Integer, default=1)

    patient:        Mapped["Patient"]               = relationship("Patient",       back_populates="prescriptions")
    prescriber:     Mapped["User"]                  = relationship("User",          back_populates="prescriptions")
    medication:     Mapped[Optional["Medication"]]  = relationship("Medication",    back_populates="prescriptions")
    treatment_plan: Mapped[Optional["TreatmentPlan"]] = relationship("TreatmentPlan", back_populates="prescriptions")
    safety_checks:  Mapped[List["SafetyCheck"]]     = relationship("SafetyCheck",   back_populates="prescription", cascade="all, delete-orphan")


# ─── SAFETY CHECK ─────────────────────────────────────────
class SafetyCheck(Base):
    __tablename__ = "safety_checks"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    prescription_id: Mapped[int] = mapped_column(Integer, ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    check_type: Mapped[str]      = mapped_column(String(50))   # drug_drug / drug_allergy / dosage / contraindication
    result: Mapped[SafetyResult] = mapped_column(SAEnum(SafetyResult))
    severity: Mapped[Optional[str]] = mapped_column(String(50))
    findings: Mapped[Optional[str]] = mapped_column(Text)
    alternatives: Mapped[Optional[dict]] = mapped_column(JSON)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    prescription: Mapped["Prescription"] = relationship("Prescription", back_populates="safety_checks")


# ─── AUDIT LOG ────────────────────────────────────────────
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int]              = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    action: Mapped[str]          = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50))   # patient / diagnosis / prescription
    resource_id: Mapped[Optional[int]]   = mapped_column(Integer)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    log_type: Mapped[str]        = mapped_column(String(30), default="data")  # auth / data / clinical / prescription
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
