"""
Pydantic v2 schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List, Any, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
import re


# ─── AUTH ─────────────────────────────────────────────────
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    password: str
    role: Literal["physician", "nurse", "pharmacist", "patient"] = "physician"
    license_number: Optional[str] = None
    profile_image: Optional[str] = Field(None, description="Optional data URL image (JPEG/PNG)")
    # Extra fields required only when role=patient
    date_of_birth: Optional[str] = None   # YYYY-MM-DD
    gender: Optional[str] = None          # Male / Female / Other

    @field_validator("username", "full_name", mode="before")
    @classmethod
    def strip_text(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters (NFR5)")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain an uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain a lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain a digit")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    license_number: Optional[str]
    profile_image: Optional[str] = None
    is_active: bool
    last_login: Optional[datetime]
    linked_patient_id: Optional[int] = None

    model_config = {"from_attributes": True}


# ─── PATIENT ──────────────────────────────────────────────
class AllergyCreate(BaseModel):
    allergen: str
    allergy_type: str = "Drug"
    severity: str = "Moderate"
    reaction: Optional[str] = None


class AllergyOut(AllergyCreate):
    id: int
    patient_id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class MedicalHistoryCreate(BaseModel):
    condition: str
    icd_code: Optional[str] = None
    diagnosed_date: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool = True


class MedicalHistoryOut(MedicalHistoryCreate):
    id: int
    patient_id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class PatientCreate(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: str
    gender: str
    weight: Optional[float] = None
    height: Optional[float] = None
    blood_type: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    allergies: Optional[List[AllergyCreate]] = []
    conditions: Optional[List[MedicalHistoryCreate]] = []


class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    weight: Optional[float] = None
    height: Optional[float] = None
    blood_type: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    version: int  # required for optimistic locking


class PatientOut(BaseModel):
    id: int
    mrn: str
    first_name: str
    last_name: str
    full_name: str
    date_of_birth: str
    gender: str
    weight: Optional[float]
    height: Optional[float]
    blood_type: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    version: int
    allergies: List[AllergyOut] = []
    medical_histories: List[MedicalHistoryOut] = []

    model_config = {"from_attributes": True}


# ─── CLINICAL NOTES ───────────────────────────────────────
class ClinicalNoteCreate(BaseModel):
    patient_id: int
    note_text: str
    symptoms: Optional[str] = None
    observations: Optional[str] = None


class ClinicalNoteOut(BaseModel):
    id: int
    patient_id: int
    author_id: int
    note_text: str
    symptoms: Optional[str]
    observations: Optional[str]
    extracted_entities: Optional[Any]
    note_date: datetime
    created_at: datetime
    model_config = {"from_attributes": True}


# ─── DIAGNOSIS ────────────────────────────────────────────
class DxFactorIn(BaseModel):
    n: str
    v: int

    @field_validator("v", mode="before")
    @classmethod
    def coerce_factor_v(cls, v):
        try:
            return max(0, min(100, int(round(float(v)))))
        except (TypeError, ValueError):
            return 0


class DxSuggestionIn(BaseModel):
    rank: int
    name: str
    icd: str
    confidence: int
    evidence: str
    factors: List[DxFactorIn] = Field(default_factory=list)

    @field_validator("rank", mode="before")
    @classmethod
    def coerce_rank(cls, v):
        try:
            return max(1, int(round(float(v))))
        except (TypeError, ValueError):
            return 1

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v):
        try:
            return max(0, min(100, int(round(float(v)))))
        except (TypeError, ValueError):
            return 0


class LLMDiagnosisRequest(BaseModel):
    """Payload for LLM differential diagnosis (no PHI beyond what the clinician enters)."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symptoms": "Fever and sore throat for 3 days",
                "patient_name": "Demo Patient",
                "age": "40",
                "gender": "Female",
                "conditions": ["Hypertension"],
                "allergies": [],
                "clinical_notes": None,
                "lab": {"glucose": "110"},
            }
        }
    )

    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    age: Optional[str] = None
    gender: Optional[str] = None
    conditions: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    symptoms: str
    clinical_notes: Optional[str] = None
    lab: Optional[dict] = None

    @field_validator("lab", mode="before")
    @classmethod
    def lab_must_be_object_or_empty(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, dict):
            return v
        raise ValueError("lab must be a JSON object (e.g. {}) or null, not a string or array")


class LLMDiagnosisResponse(BaseModel):
    suggestions: List[DxSuggestionIn]
    model: str
    llm_used: bool = True


class LLMStatusOut(BaseModel):
    configured: bool
    model: str


class DiagnosisCreate(BaseModel):
    patient_id: int
    diagnosis_name: str
    diagnosis_code: Optional[str] = None
    confidence_score: Optional[float] = None
    source: str = "AI+Physician"
    notes: Optional[str] = None
    ai_suggestions: Optional[Any] = None   # full ranked list to store
    shap_values: Optional[Any] = None
    reasoning: Optional[str] = None


class DiagnosisUpdate(BaseModel):
    status: Optional[str] = None
    is_confirmed: Optional[bool] = None
    notes: Optional[str] = None
    version: int


class AIAnalysisOut(BaseModel):
    id: int
    model_version: str
    confidence_score: float
    shap_values: Optional[Any]
    lime_values: Optional[Any]
    feature_importance: Optional[Any]
    reasoning: Optional[str]
    all_suggestions: Optional[Any]
    analysed_at: datetime
    model_config = {"from_attributes": True}


class DiagnosisOut(BaseModel):
    id: int
    patient_id: int
    physician_id: int
    diagnosis_name: str
    diagnosis_code: Optional[str]
    confidence_score: Optional[float]
    status: str
    source: str
    is_confirmed: bool
    notes: Optional[str]
    diagnosed_at: datetime
    created_at: datetime
    version: int
    ai_analysis: Optional[AIAnalysisOut] = None
    model_config = {"from_attributes": True}


# ─── TREATMENT PLAN ───────────────────────────────────────
class TreatmentPlanCreate(BaseModel):
    patient_id: int
    diagnosis_id: int
    title: str
    treatment_description: str
    medications: Optional[List[Any]] = []
    lifestyle: Optional[List[str]] = []
    monitoring: Optional[List[str]] = []
    references: Optional[List[str]] = []


class TreatmentPlanOut(BaseModel):
    id: int
    patient_id: int
    diagnosis_id: int
    title: str
    treatment_description: str
    medications: Optional[Any]
    lifestyle: Optional[Any]
    monitoring: Optional[Any]
    references: Optional[Any]
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ─── MEDICATION ───────────────────────────────────────────
class MedicationOut(BaseModel):
    id: int
    generic_name: str
    brand_names: Optional[str]
    drug_class: Optional[str]
    indication: Optional[str]
    contraindications: Optional[Any]
    common_interactions: Optional[Any]
    max_daily_dose: Optional[str]
    model_config = {"from_attributes": True}


# ─── PRESCRIPTION ─────────────────────────────────────────
class PrescriptionCreate(BaseModel):
    patient_id: int
    drug_name: str
    dose: str
    frequency: str
    route: str = "Oral"
    duration: str
    special_instructions: Optional[str] = None
    medication_id: Optional[int] = None
    treatment_plan_id: Optional[int] = None


class SafetyCheckOut(BaseModel):
    id: int
    check_type: str
    result: str
    severity: Optional[str]
    findings: Optional[str]
    alternatives: Optional[Any]
    checked_at: datetime
    model_config = {"from_attributes": True}


class PrescriptionOut(BaseModel):
    id: int
    patient_id: int
    prescriber_id: int
    drug_name: str
    dose: str
    frequency: str
    route: str
    duration: str
    special_instructions: Optional[str]
    status: str
    prescribed_date: datetime
    created_at: datetime
    version: int
    safety_checks: List[SafetyCheckOut] = []
    model_config = {"from_attributes": True}


# ─── AUDIT LOG ────────────────────────────────────────────
class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    detail: Optional[str]
    ip_address: Optional[str]
    log_type: str
    created_at: datetime
    model_config = {"from_attributes": True}


class AuditLogWithUserOut(BaseModel):
    """Audit row with actor identity (admin audit viewer)."""
    id: int
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    detail: Optional[str] = None
    ip_address: Optional[str] = None
    log_type: str
    created_at: datetime


# ─── DRUG SAFETY ──────────────────────────────────────────
class DrugSafetyRequest(BaseModel):
    patient_id: int
    drug_name: str
    dose: Optional[str] = None


class DrugSafetyResponse(BaseModel):
    safe: bool
    result_type: str          # safe / warning / critical / blocked
    title: str
    message: str
    blocked: bool
    checks: List[dict]
    alternatives: List[str] = []


# ─── PAGINATION ───────────────────────────────────────────
class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int
