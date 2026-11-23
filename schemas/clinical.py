from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)

AppointmentType = Literal[
    "anc_visit", "ultrasound", "lab_test", "postnatal_checkup", "specialist"
]


class ClinicalSchema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class PatientProfileUpdate(ClinicalSchema):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: str | None = Field(default=None, min_length=5, max_length=100)
    age: int | None = Field(default=None, ge=10, le=70)
    phone_number: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=255)
    emergency_contact_name: str | None = Field(default=None, max_length=100)
    emergency_contact_phone: str | None = Field(default=None, max_length=20)
    due_date: Date | None = None
    gestation_week: int | None = Field(default=None, ge=1, le=45)
    gravida: int | None = Field(default=None, ge=1)
    para: int | None = Field(default=None, ge=0)
    blood_type: str | None = Field(default=None, max_length=20)
    allergies: list[str] | None = None
    medical_conditions: list[str] | None = None
    risk_status: Literal["low", "moderate", "high"] | None = None


class SymptomCreate(ClinicalSchema):
    symptom_name: str = Field(min_length=1, max_length=150)
    category: Literal[
        "digestive", "pain", "neurological", "respiratory", "fetal",
        "bleeding", "systemic", "other"
    ] = "other"
    severity: Literal["mild", "moderate", "severe"]
    notes: str = Field(default="", max_length=1000)
    gestation_week: int = Field(ge=1, le=45)
    ai_assessment: dict | None = None


class SymptomReview(ClinicalSchema):
    note: str = Field(min_length=1, max_length=1000)


class AppointmentCreate(ClinicalSchema):
    title: str = Field(min_length=1, max_length=255)
    appointment_type: AppointmentType = "anc_visit"
    date: Date
    time: str = Field(min_length=1, max_length=30)
    facility_id: int | None = None
    facility: str = Field(default="", max_length=255)
    provider_name: str = Field(default="", max_length=150)
    status: Literal[
        "upcoming", "completed", "cancelled", "rescheduled"
    ] = "upcoming"
    notes: str | None = Field(default=None, max_length=1000)
    patient_id: int | None = Field(default=None, gt=0)


class AppointmentUpdate(ClinicalSchema):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    appointment_type: AppointmentType | None = None
    date: Date | None = None
    time: str | None = Field(default=None, min_length=1, max_length=30)
    facility_id: int | None = None
    facility: str | None = Field(default=None, max_length=255)
    provider_name: str | None = Field(default=None, max_length=150)
    status: Literal[
        "upcoming", "completed", "cancelled", "rescheduled"
    ] | None = None
    notes: str | None = Field(default=None, max_length=1000)


class MessageCreate(ClinicalSchema):
    content: str = Field(min_length=1, max_length=2000)
    is_urgent: bool = False
    is_audio: bool = False
    audio_duration: str | None = Field(default=None, max_length=20)
    patient_id: int | None = Field(default=None, gt=0)


class MedicationCreate(ClinicalSchema):
    name: str = Field(min_length=1, max_length=150)
    dosage: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    time_of_day: list[str] = Field(min_length=1, max_length=12)
    purpose: str = Field(default="", max_length=500)
    safety_category: Literal["A", "B", "C"] | None = None


class MedicationUpdate(ClinicalSchema):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    dosage: str | None = Field(default=None, min_length=1, max_length=100)
    frequency: str | None = Field(default=None, min_length=1, max_length=100)
    time_of_day: list[str] | None = Field(default=None, min_length=1, max_length=12)
    purpose: str | None = Field(default=None, max_length=500)
    safety_category: Literal["A", "B", "C"] | None = None


class MedicationDoseUpdate(ClinicalSchema):
    dose_index: int = Field(ge=0)
    taken: bool


class AlertUpdate(ClinicalSchema):
    is_read: bool | None = None
    is_resolved: bool | None = None


class EmergencyCreate(ClinicalSchema):
    notes: str | None = Field(default=None, max_length=1000)


class KickSessionCreate(ClinicalSchema):
    date: Date
    start_time: str = Field(min_length=1, max_length=30)
    duration_minutes: int = Field(gt=0, le=1440)
    kick_count: int = Field(ge=0, le=1000)
    notes: str | None = Field(default=None, max_length=1000)


class ContractionCreate(ClinicalSchema):
    duration_seconds: int = Field(gt=0, le=3600)
    interval_minutes: int = Field(ge=0, le=1440)
    intensity: Literal["mild", "moderate", "strong"]


class ArticleCreate(ClinicalSchema):
    title: str = Field(min_length=1, max_length=255)
    category: str = Field(default="other", max_length=100)
    read_time: str = Field(default="", max_length=30)
    summary: str = Field(default="", max_length=1000)
    content: list[str] = Field(default_factory=list)
    key_takeaways: list[str] = Field(default_factory=list)
    evidence_source: str = Field(default="", max_length=255)
    danger_sign: bool = False


class ArticleUpdate(ClinicalSchema):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    read_time: str | None = Field(default=None, max_length=30)
    summary: str | None = Field(default=None, max_length=1000)
    content: list[str] | None = None
    key_takeaways: list[str] | None = None
    evidence_source: str | None = Field(default=None, max_length=255)
    danger_sign: bool | None = None


class FacilityCreate(ClinicalSchema):
    name: str = Field(min_length=1, max_length=150)
    facility_type: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=255)
    district: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=100)
    distance_km: int = Field(default=0, ge=0)
    estimated_drive_time_mins: int = Field(default=0, ge=0)
    emergency_hotline: str = Field(default="", max_length=30)
    maternity_beds_available: int = Field(default=0, ge=0)
    has_nic_unit: bool = False
    open_24_hours: bool = False


class FacilityUpdate(ClinicalSchema):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    facility_type: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=255)
    district: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=100)
    distance_km: int | None = Field(default=None, ge=0)
    estimated_drive_time_mins: int | None = Field(default=None, ge=0)
    emergency_hotline: str | None = Field(default=None, max_length=30)
    maternity_beds_available: int | None = Field(default=None, ge=0)
    has_nic_unit: bool | None = None
    open_24_hours: bool | None = None


class KnowledgeRuleCreate(ClinicalSchema):
    category: Literal[
        "clinical_protocol", "danger_sign", "nutrition", "non_diagnostic", "who_guideline"
    ]
    title: str = Field(min_length=1, max_length=255)
    guideline: str = Field(min_length=1, max_length=5000)
    evidence_source: str = Field(default="", max_length=255)
    is_active: bool = True
    is_red_flag_trigger: bool = False


class KnowledgeRuleUpdate(ClinicalSchema):
    category: Literal[
        "clinical_protocol", "danger_sign", "nutrition", "non_diagnostic", "who_guideline"
    ] | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    guideline: str | None = Field(default=None, min_length=1, max_length=5000)
    evidence_source: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_red_flag_trigger: bool | None = None


class AiAuditCreate(ClinicalSchema):
    gestation_week: int = Field(ge=1, le=45)
    prompt: str = Field(min_length=1, max_length=2000)
    response_summary: str = Field(min_length=1, max_length=2000)
    non_diagnostic_score: int = Field(default=100, ge=0, le=100)
    red_flag_detected: bool = False


class AiAuditUpdate(ClinicalSchema):
    status: Literal["safe", "flagged", "reviewed"]


class SystemActivityCreate(ClinicalSchema):
    action_type: Literal[
        "login", "user_created", "user_status_changed", "symptom_logged",
        "appointment_scheduled", "nurse_review", "emergency_sos",
        "content_updated"
    ]
    description: str = Field(min_length=1, max_length=1000)


class AdminReportCreate(ClinicalSchema):
    title: str = Field(min_length=1, max_length=255)
    period: str = Field(default="Active Real-Time Audit", max_length=100)


class AdminUserCreate(ClinicalSchema):
    username: str = Field(min_length=3, max_length=50)
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: str = Field(min_length=5, max_length=100)
    password: str = Field(min_length=8)
    role: Literal["patient", "nurse", "admin"]
    phone_number: str | None = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    facility_id: int | None = Field(default=None, gt=0)
    professional_registration_number: str | None = Field(
        default=None, max_length=100
    )
    gestation_week: int | None = Field(default=None, ge=1, le=45)
    assigned_nurse_id: int | None = Field(default=None, gt=0)
    age: int | None = Field(default=None, ge=10, le=70)
    due_date: Date | None = None
    gravida: int | None = Field(default=None, ge=1)
    para: int | None = Field(default=None, ge=0)
    blood_type: str | None = Field(default=None, max_length=20)
    allergies: list[str] = Field(default_factory=list)
    medical_conditions: list[str] = Field(default_factory=list)


class AdminUserUpdate(ClinicalSchema):
    username: str | None = Field(default=None, min_length=3, max_length=50)
    email: str | None = Field(default=None, min_length=5, max_length=100)
    is_active: bool | None = None


class NurseAssignment(ClinicalSchema):
    nurse_id: int = Field(gt=0)
    facility_id: int | None = Field(default=None, gt=0)
