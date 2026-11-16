from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.security.password import hash_password
from backend.schemas.clinical import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminReportCreate,
    AiAuditCreate,
    AiAuditUpdate,
    AlertUpdate,
    AppointmentCreate,
    AppointmentUpdate,
    ArticleCreate,
    ArticleUpdate,
    ContractionCreate,
    EmergencyCreate,
    FacilityCreate,
    FacilityUpdate,
    KnowledgeRuleCreate,
    KnowledgeRuleUpdate,
    KickSessionCreate,
    MedicationCreate,
    MedicationDoseUpdate,
    MedicationUpdate,
    MessageCreate,
    NurseAssignment,
    PatientProfileUpdate,
    SystemActivityCreate,
    SymptomCreate,
    SymptomReview,
)
from database.database import get_db
from database.models import (
    Appointment,
    AppointmentClinicalDetail,
    AdminReportRecord,
    AiAuditRecord,
    AiKnowledgeRuleRecord,
    ContractionLog,
    EducationalArticleRecord,
    EmergencyAlert,
    Facility,
    FacilityServiceDetail,
    KickSession,
    Medication,
    Message,
    MessageClinicalDetail,
    Nurse,
    NurseAlert,
    Patient,
    PatientProfile,
    Pregnancy,
    ITPersonnel,
    SymptomClinicalDetail,
    SymptomLog,
    SystemActivityRecord,
    User,
)

router = APIRouter(tags=["Clinical Care"])


def _patient_for_user(db: Session, user: User) -> Patient:
    patient = db.query(Patient).filter(Patient.user_id == user.user_id).first()
    if patient is None:
        if user.role != "patient":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient record was not found.",
            )
        patient = Patient(user_id=user.user_id)
        db.add(patient)
        db.flush()
        db.add(PatientProfile(patient_id=patient.patient_id))
        db.add(Pregnancy(patient_id=patient.patient_id))
        db.flush()
    elif db.query(PatientProfile).filter(
        PatientProfile.patient_id == patient.patient_id
    ).first() is None:
        db.add(PatientProfile(patient_id=patient.patient_id))
        db.flush()
    return patient


def _profile_for_patient(db: Session, patient_id: int) -> PatientProfile:
    profile = db.query(PatientProfile).filter(
        PatientProfile.patient_id == patient_id
    ).first()
    if profile is None:
        profile = PatientProfile(patient_id=patient_id)
        db.add(profile)
        db.flush()
    return profile


def _nurse_for_user(db: Session, user: User) -> Nurse:
    nurse = db.query(Nurse).filter(Nurse.user_id == user.user_id).first()
    if nurse is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is not associated with a nurse profile.",
        )
    return nurse


def _accessible_patient(
    db: Session, patient_id: int, user: User
) -> Patient:
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient was not found.")
    if user.role == "admin":
        return patient
    if user.role == "patient" and patient.user_id == user.user_id:
        return patient
    if user.role == "nurse":
        nurse = _nurse_for_user(db, user)
        profile = _profile_for_patient(db, patient.patient_id)
        if profile.assigned_nurse_id == nurse.nurse_id:
            return patient
    raise HTTPException(status_code=403, detail="You cannot access this patient.")


def _patient_profile_response(
    db: Session, patient: Patient, user: User | None = None
) -> dict:
    profile = _profile_for_patient(db, patient.patient_id)
    if user is None:
        user = db.query(User).filter(User.user_id == patient.user_id).first()
    nurse = db.query(Nurse).filter(
        Nurse.nurse_id == profile.assigned_nurse_id
    ).first() if profile.assigned_nurse_id else None
    nurse_user = db.query(User).filter(
        User.user_id == nurse.user_id
    ).first() if nurse else None
    facility = db.query(Facility).filter(
        Facility.facility_id == profile.assigned_facility_id
    ).first() if profile.assigned_facility_id else None
    return {
        "id": f"patient-{patient.patient_id}",
        "userId": str(patient.user_id),
        "name": (patient.full_name or user.username) if user else "",
        "email": user.email if user else "",
        "age": profile.age or 0,
        "phone": patient.phone_number or "",
        "address": patient.address or "",
        "dueDate": profile.due_date.isoformat() if profile.due_date else "",
        "gestationWeek": profile.gestation_week or 1,
        "gravida": profile.gravida,
        "para": profile.para,
        "bloodType": profile.blood_type or "",
        "riskStatus": profile.risk_status,
        "allergies": profile.allergies or [],
        "medicalConditions": profile.medical_conditions or [],
        "assignedNurseId": (
            f"nurse-{profile.assigned_nurse_id}"
            if profile.assigned_nurse_id else ""
        ),
        "assignedNurseName": nurse_user.username if nurse_user else "",
        "assignedFacility": facility.facility_name if facility else "",
        "emergencyContact": {
            "name": patient.emergency_contact_name or "",
            "relationship": "",
            "phone": patient.emergency_contact_phone or "",
        },
    }


def _symptom_response(
    symptom: SymptomLog, detail: SymptomClinicalDetail | None
) -> dict:
    return {
        "id": f"sym-{symptom.symptom_log_id}",
        "timestamp": symptom.recorded_at.isoformat() if symptom.recorded_at else "",
        "symptomName": detail.symptom_name if detail else symptom.symptoms,
        "category": detail.category if detail else "other",
        "severity": symptom.severity or "mild",
        "notes": symptom.notes or "",
        "gestationWeek": detail.gestation_week if detail else 1,
        "aiAssessment": detail.ai_assessment if detail else None,
        "reviewedByNurse": detail.reviewed_by_nurse if detail else False,
        "nurseReviewNote": detail.nurse_review_note if detail else None,
        "reviewedAt": detail.reviewed_at.isoformat() if detail and detail.reviewed_at else None,
    }


def _appointment_response(
    appointment: Appointment,
    facility: Facility | None,
    detail: AppointmentClinicalDetail | None = None,
) -> dict:
    appointment_time = appointment.appointment_date
    return {
        "id": f"apt-{appointment.appointment_id}",
        "title": appointment.purpose or "Antenatal care visit",
        "type": detail.appointment_type if detail else "anc_visit",
        "date": appointment_time.date().isoformat(),
        "time": appointment_time.strftime("%I:%M %p").lstrip("0"),
        "facility": facility.facility_name if facility else "",
        "providerName": detail.provider_name if detail else "",
        "status": (
            appointment.status if appointment.status in {
                "upcoming", "completed", "cancelled", "rescheduled"
            } else "upcoming"
        ),
        "notes": appointment.notes or "",
    }


def _parse_appointment_time(day: date, value: str) -> datetime:
    try:
        parsed_time = time.fromisoformat(value)
    except ValueError:
        try:
            parsed_time = datetime.strptime(value, "%I:%M %p").time()
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="Appointment time must use HH:MM or h:MM AM/PM format.",
            ) from error
    return datetime.combine(day, parsed_time)


def _alert_response(alert: NurseAlert) -> dict:
    patient = alert.patient_id
    return {
        "id": f"alt-{alert.alert_id}",
        "patientId": f"patient-{patient}",
        "patientName": "",
        "type": alert.alert_type,
        "urgency": alert.urgency,
        "message": alert.message,
        "timestamp": alert.created_at.isoformat() if alert.created_at else "",
        "isRead": alert.is_read,
        "isResolved": alert.is_resolved,
    }


def _medication_response(medication: Medication) -> dict:
    doses_taken = medication.doses_taken or []
    if medication.dose_log_date != date.today():
        doses_taken = [False] * len(medication.time_of_day or [])
    return {
        "id": f"med-{medication.medication_id}",
        "patientId": f"patient-{medication.patient_id}",
        "name": medication.name,
        "dosage": medication.dosage,
        "frequency": medication.frequency,
        "timeOfDay": medication.time_of_day or [],
        "purpose": medication.purpose,
        "safetyCategory": medication.safety_category or "B",
        "takenToday": doses_taken,
        "lastTakenDate": (
            medication.last_taken_date.isoformat()
            if medication.last_taken_date else None
        ),
        "streakDays": medication.streak_days,
    }


def _article_response(article: EducationalArticleRecord) -> dict:
    return {
        "id": f"art-{article.article_id}",
        "title": article.title,
        "category": article.category,
        "readTime": article.read_time,
        "summary": article.summary,
        "content": article.content or [],
        "keyTakeaways": article.key_takeaways or [],
        "evidenceSource": article.evidence_source,
        "dangerSign": article.danger_sign,
    }


@router.get("/patients/me/profile")
def get_my_patient_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient account required.")
    patient = _patient_for_user(db, current_user)
    db.commit()
    return _patient_profile_response(db, patient, current_user)


@router.put("/patients/me/profile")
def update_my_patient_profile(
    updates: PatientProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient account required.")
    patient = _patient_for_user(db, current_user)
    profile = _profile_for_patient(db, patient.patient_id)
    data = updates.model_dump(exclude_unset=True)

    username = data.pop("username", None)
    email = data.pop("email", None)
    full_name = data.pop("full_name", None)
    if full_name is not None:
        patient.full_name = full_name
    for field in ("phone_number", "address", "emergency_contact_name", "emergency_contact_phone"):
        if field in data:
            setattr(patient, field, data.pop(field))
    for field, value in data.items():
        setattr(profile, field, value)

    if username is not None:
        duplicate = db.query(User).filter(
            User.username == username,
            User.user_id != current_user.user_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Username is already in use.")
        current_user.username = username
    if email is not None:
        duplicate = db.query(User).filter(
            User.email == email,
            User.user_id != current_user.user_id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="Email is already in use.")
        current_user.email = email

    db.commit()
    db.refresh(patient)
    db.refresh(profile)
    return _patient_profile_response(db, patient, current_user)


@router.patch("/patients/{patient_id}/profile")
def update_patient_profile(
    patient_id: int,
    updates: PatientProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role not in {"nurse", "admin"}:
        raise HTTPException(status_code=403, detail="Clinical staff access required.")
    patient = _accessible_patient(db, patient_id, current_user)
    profile = _profile_for_patient(db, patient.patient_id)
    values = updates.model_dump(exclude_unset=True)
    full_name = values.pop("full_name", None)
    if full_name is not None:
        patient.full_name = full_name
    username = values.pop("username", None)
    email = values.pop("email", None)
    for field in (
        "phone_number", "address",
        "emergency_contact_name", "emergency_contact_phone",
    ):
        if field in values:
            setattr(patient, field, values.pop(field))
    for field, value in values.items():
        setattr(profile, field, value)
    account = db.query(User).filter(User.user_id == patient.user_id).first()
    if account is not None and username is not None:
        if db.query(User).filter(
            User.username == username,
            User.user_id != account.user_id,
        ).first():
            raise HTTPException(status_code=409, detail="Username is already in use.")
        account.username = username
    if account is not None and email is not None:
        if db.query(User).filter(
            User.email == email,
            User.user_id != account.user_id,
        ).first():
            raise HTTPException(status_code=409, detail="Email is already in use.")
        account.email = email
    db.commit()
    db.refresh(patient)
    db.refresh(profile)
    return _patient_profile_response(db, patient, account)


@router.get("/patients")
def list_patients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "patient":
        raise HTTPException(status_code=403, detail="Clinical staff access required.")
    query = db.query(Patient)
    if current_user.role == "nurse":
        nurse = _nurse_for_user(db, current_user)
        query = query.join(
            PatientProfile,
            PatientProfile.patient_id == Patient.patient_id,
        ).filter(PatientProfile.assigned_nurse_id == nurse.nurse_id)
    patients = query.order_by(Patient.patient_id).all()
    return [_patient_profile_response(db, patient) for patient in patients]


@router.get("/nurses")
def list_nurses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.query(Nurse).order_by(Nurse.nurse_id).all()
    result = []
    for nurse in rows:
        user = db.query(User).filter(User.user_id == nurse.user_id).first()
        facility = db.query(Facility).filter(
            Facility.facility_id == nurse.facility_id
        ).first() if nurse.facility_id else None
        assigned_count = db.query(PatientProfile).filter(
            PatientProfile.assigned_nurse_id == nurse.nurse_id
        ).count()
        result.append({
            "id": f"nurse-{nurse.nurse_id}",
            "userId": nurse.user_id,
            "name": user.username if user else "",
            "email": user.email if user else "",
            "phone": nurse.phone_number or "",
            "department": nurse.specialization or "",
            "facility": facility.facility_name if facility else "",
            "professionalRegistrationNumber": nurse.professional_registration_number or "",
            "activePatientsCount": assigned_count,
            "title": nurse.specialization or "Nurse",
            "avatar": "",
            "isOnline": False,
            "dutyHours": "",
        })
    return result


@router.get("/admin/users")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return [
        {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
        }
        for user in db.query(User).order_by(User.created_at.desc()).all()
    ]


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
def create_staff_or_patient_user(
    user_data: AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    if db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first():
        raise HTTPException(status_code=409, detail="Username or email is already in use.")
    if user_data.role == "nurse" and user_data.facility_id:
        if db.query(Facility).filter(
            Facility.facility_id == user_data.facility_id
        ).first() is None:
            raise HTTPException(status_code=404, detail="Facility was not found.")
    if user_data.role == "patient" and user_data.assigned_nurse_id:
        if db.query(Nurse).filter(
            Nurse.nurse_id == user_data.assigned_nurse_id
        ).first() is None:
            raise HTTPException(status_code=404, detail="Nurse was not found.")

    account = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        role=user_data.role,
        is_active=True,
    )
    db.add(account)
    try:
        db.flush()
        if user_data.role == "patient":
            patient = Patient(
                user_id=account.user_id,
                phone_number=user_data.phone_number,
                full_name=user_data.full_name,
            )
            db.add(patient)
            db.flush()
            db.add(PatientProfile(
                patient_id=patient.patient_id,
                age=user_data.age,
                due_date=user_data.due_date,
                gestation_week=user_data.gestation_week,
                gravida=user_data.gravida or 1,
                para=user_data.para or 0,
                blood_type=user_data.blood_type,
                allergies=user_data.allergies,
                medical_conditions=user_data.medical_conditions,
                assigned_nurse_id=user_data.assigned_nurse_id,
                assigned_facility_id=(
                    db.query(Nurse.facility_id).filter(
                        Nurse.nurse_id == user_data.assigned_nurse_id
                    ).scalar()
                    if user_data.assigned_nurse_id else None
                ),
            ))
            db.add(Pregnancy(
                patient_id=patient.patient_id,
                expected_delivery_date=user_data.due_date,
            ))
        elif user_data.role == "nurse":
            db.add(Nurse(
                user_id=account.user_id,
                facility_id=user_data.facility_id,
                professional_registration_number=(
                    user_data.professional_registration_number
                ),
                phone_number=user_data.phone_number,
                specialization=user_data.department,
            ))
        else:
            db.add(ITPersonnel(
                user_id=account.user_id,
                phone_number=user_data.phone_number,
                department=user_data.department,
            ))
        db.commit()
        db.refresh(account)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Username, email, or professional registration number is already in use.",
        ) from error
    return {
        "user_id": account.user_id,
        "username": account.username,
        "email": account.email,
        "role": account.role,
        "is_active": account.is_active,
        "created_at": account.created_at,
    }


@router.patch("/admin/users/{user_id}")
def update_user_account(
    user_id: int,
    updates: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    account = db.query(User).filter(User.user_id == user_id).first()
    if account is None:
        raise HTTPException(status_code=404, detail="User was not found.")
    values = updates.model_dump(exclude_unset=True)
    for field in ("username", "email"):
        value = values.get(field)
        if value is not None:
            duplicate = db.query(User).filter(
                getattr(User, field) == value,
                User.user_id != user_id,
            ).first()
            if duplicate:
                raise HTTPException(
                    status_code=409,
                    detail=f"{field.capitalize()} is already in use.",
                )
            setattr(account, field, value)
    if "is_active" in values:
        if account.user_id == current_user.user_id and not values["is_active"]:
            raise HTTPException(
                status_code=409,
                detail="You cannot deactivate your own administrator account.",
            )
        account.is_active = values["is_active"]
    db.commit()
    db.refresh(account)
    return {
        "user_id": account.user_id,
        "username": account.username,
        "email": account.email,
        "role": account.role,
        "is_active": account.is_active,
        "created_at": account.created_at,
    }


@router.put("/patients/{patient_id}/nurse")
def assign_patient_nurse(
    patient_id: int,
    assignment: NurseAssignment,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    nurse = db.query(Nurse).filter(Nurse.nurse_id == assignment.nurse_id).first()
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient was not found.")
    if nurse is None:
        raise HTTPException(status_code=404, detail="Nurse was not found.")
    facility_id = assignment.facility_id or nurse.facility_id
    if facility_id and db.query(Facility).filter(
        Facility.facility_id == facility_id
    ).first() is None:
        raise HTTPException(status_code=404, detail="Facility was not found.")
    profile = _profile_for_patient(db, patient.patient_id)
    profile.assigned_nurse_id = nurse.nurse_id
    profile.assigned_facility_id = facility_id
    db.commit()
    account = db.query(User).filter(User.user_id == nurse.user_id).first()
    facility = db.query(Facility).filter(
        Facility.facility_id == facility_id
    ).first() if facility_id else None
    response = _patient_profile_response(db, patient)
    response["assignedNurseName"] = account.username if account else ""
    response["assignedFacility"] = facility.facility_name if facility else ""
    return response


@router.get("/symptoms")
def list_symptoms(
    patient_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "patient":
        patient = _patient_for_user(db, current_user)
        if patient_id is not None and patient_id != patient.patient_id:
            raise HTTPException(status_code=403, detail="You cannot access this patient.")
        patient_id = patient.patient_id
    elif patient_id is not None:
        _accessible_patient(db, patient_id, current_user)
    elif current_user.role == "nurse":
        nurse = _nurse_for_user(db, current_user)
        patient_ids = [
            row.patient_id for row in db.query(PatientProfile.patient_id).filter(
                PatientProfile.assigned_nurse_id == nurse.nurse_id
            ).all()
        ]
        if not patient_ids:
            return []
        patient_id = None
    else:
        patient_ids = None

    query = db.query(SymptomLog)
    if patient_id is not None:
        query = query.filter(SymptomLog.patient_id == patient_id)
    elif current_user.role == "nurse":
        query = query.filter(SymptomLog.patient_id.in_(patient_ids))
    symptoms = query.order_by(SymptomLog.recorded_at.desc()).all()
    return [
        _symptom_response(
            symptom,
            db.query(SymptomClinicalDetail).filter(
                SymptomClinicalDetail.symptom_log_id == symptom.symptom_log_id
            ).first(),
        )
        for symptom in symptoms
    ]


@router.post("/symptoms", status_code=status.HTTP_201_CREATED)
def create_symptom(
    symptom_data: SymptomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient account required.")
    patient = _patient_for_user(db, current_user)
    pregnancy = db.query(Pregnancy).filter(
        Pregnancy.patient_id == patient.patient_id,
        Pregnancy.pregnancy_status == "active",
    ).first()
    if pregnancy is None:
        pregnancy = Pregnancy(patient_id=patient.patient_id)
        db.add(pregnancy)
        db.flush()

    values = symptom_data.model_dump()
    symptom = SymptomLog(
        patient_id=patient.patient_id,
        pregnancy_id=pregnancy.pregnancy_id,
        symptoms=values["symptom_name"],
        severity=values["severity"],
        notes=values["notes"],
    )
    db.add(symptom)
    db.flush()
    detail = SymptomClinicalDetail(
        symptom_log_id=symptom.symptom_log_id,
        symptom_name=values["symptom_name"],
        category=values["category"],
        gestation_week=values["gestation_week"],
        ai_assessment=values["ai_assessment"],
    )
    db.add(detail)
    profile = _profile_for_patient(db, patient.patient_id)
    if values["severity"] == "severe" or (
        values["ai_assessment"]
        and values["ai_assessment"].get("riskCategory") in {"urgent_consult", "emergency"}
    ):
        profile.risk_status = "high"
        db.add(NurseAlert(
            patient_id=patient.patient_id,
            nurse_id=profile.assigned_nurse_id,
            alert_type="red_flag_symptom",
            urgency="high",
            message=f"Severe symptom reported: {values['symptom_name']}.",
        ))
    db.commit()
    db.refresh(symptom)
    db.refresh(detail)
    return _symptom_response(symptom, detail)


@router.patch("/symptoms/{symptom_id}/review")
def review_symptom(
    symptom_id: int,
    review: SymptomReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"nurse", "admin"}:
        raise HTTPException(status_code=403, detail="Clinical staff access required.")
    symptom = db.query(SymptomLog).filter(
        SymptomLog.symptom_log_id == symptom_id
    ).first()
    if symptom is None:
        raise HTTPException(status_code=404, detail="Symptom log was not found.")
    _accessible_patient(db, symptom.patient_id, current_user)
    detail = db.query(SymptomClinicalDetail).filter(
        SymptomClinicalDetail.symptom_log_id == symptom_id
    ).first()
    if detail is None:
        detail = SymptomClinicalDetail(
            symptom_log_id=symptom_id,
            symptom_name=symptom.symptoms,
        )
        db.add(detail)
    detail.reviewed_by_nurse = True
    detail.nurse_review_note = review.note
    detail.reviewed_by = current_user.user_id
    detail.reviewed_at = datetime.now(timezone.utc)
    db.query(NurseAlert).filter(
        NurseAlert.patient_id == symptom.patient_id,
        NurseAlert.alert_type == "red_flag_symptom",
        NurseAlert.is_resolved.is_(False),
    ).update({"is_resolved": True})
    db.commit()
    db.refresh(detail)
    return _symptom_response(symptom, detail)


@router.get("/appointments")
def list_appointments(
    patient_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "patient":
        patient = _patient_for_user(db, current_user)
        if patient_id is not None and patient_id != patient.patient_id:
            raise HTTPException(status_code=403, detail="You cannot access this patient.")
        patient_id = patient.patient_id
    elif patient_id is not None:
        _accessible_patient(db, patient_id, current_user)
    query = db.query(Appointment)
    if patient_id is not None:
        query = query.filter(Appointment.patient_id == patient_id)
    elif current_user.role == "nurse":
        nurse = _nurse_for_user(db, current_user)
        query = query.filter(Appointment.nurse_id == nurse.nurse_id)
    appointments = query.order_by(Appointment.appointment_date).all()
    return [
        _appointment_response(
            appointment,
            db.query(Facility).filter(
                Facility.facility_id == appointment.facility_id
            ).first(),
            db.query(AppointmentClinicalDetail).filter(
                AppointmentClinicalDetail.appointment_id == appointment.appointment_id
            ).first(),
        )
        for appointment in appointments
    ]


@router.post("/appointments", status_code=status.HTTP_201_CREATED)
def create_appointment(
    appointment_data: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "patient":
        patient = _patient_for_user(db, current_user)
    else:
        if appointment_data.patient_id is None:
            raise HTTPException(status_code=422, detail="patientId is required.")
        patient = _accessible_patient(db, appointment_data.patient_id, current_user)
    profile = _profile_for_patient(db, patient.patient_id)

    if current_user.role == "nurse":
        nurse = _nurse_for_user(db, current_user)
        if profile.assigned_nurse_id != nurse.nurse_id:
            raise HTTPException(status_code=403, detail="Patient is not assigned to you.")
    else:
        nurse = db.query(Nurse).filter(
            Nurse.nurse_id == profile.assigned_nurse_id
        ).first() if profile.assigned_nurse_id else None
    nurse_id = nurse.nurse_id if nurse else None
    facility_id = appointment_data.facility_id or profile.assigned_facility_id
    facility = db.query(Facility).filter(
        Facility.facility_id == facility_id
    ).first() if facility_id else None
    if appointment_data.facility and facility is None:
        facility = db.query(Facility).filter(
            Facility.facility_name == appointment_data.facility
        ).first()
    if nurse_id is None or facility is None:
        raise HTTPException(
            status_code=409,
            detail="Assign a nurse and facility to this patient before scheduling.",
        )
    appointment = Appointment(
        patient_id=patient.patient_id,
        nurse_id=nurse_id,
        facility_id=facility.facility_id,
        appointment_date=_parse_appointment_time(
            appointment_data.date, appointment_data.time
        ),
        purpose=appointment_data.title,
        status=appointment_data.status,
        notes=appointment_data.notes,
    )
    db.add(appointment)
    db.flush()
    appointment_detail = AppointmentClinicalDetail(
        appointment_id=appointment.appointment_id,
        appointment_type=appointment_data.appointment_type,
        provider_name=appointment_data.provider_name,
    )
    db.add(appointment_detail)
    db.commit()
    db.refresh(appointment)
    return _appointment_response(appointment, facility, appointment_detail)


@router.patch("/appointments/{appointment_id}")
def update_appointment(
    appointment_id: int,
    updates: AppointmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    appointment = db.query(Appointment).filter(
        Appointment.appointment_id == appointment_id
    ).first()
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment was not found.")
    if current_user.role == "patient":
        patient = _patient_for_user(db, current_user)
        if appointment.patient_id != patient.patient_id:
            raise HTTPException(status_code=403, detail="You cannot access this appointment.")
    else:
        _accessible_patient(db, appointment.patient_id, current_user)
    data = updates.model_dump(exclude_unset=True)
    if "date" in data or "time" in data:
        old_date = appointment.appointment_date.date()
        old_time = appointment.appointment_date.strftime("%H:%M")
        appointment.appointment_date = _parse_appointment_time(
            data.pop("date", old_date),
            data.pop("time", old_time),
        )
    if "title" in data:
        appointment.purpose = data.pop("title")
    if "appointment_type" in data:
        appointment_detail = db.query(AppointmentClinicalDetail).filter(
            AppointmentClinicalDetail.appointment_id == appointment.appointment_id
        ).first()
        if appointment_detail is None:
            appointment_detail = AppointmentClinicalDetail(
                appointment_id=appointment.appointment_id
            )
            db.add(appointment_detail)
        appointment_detail.appointment_type = data.pop("appointment_type")
    if "facility" in data:
        data.pop("facility")
    if "provider_name" in data:
        appointment_detail = db.query(AppointmentClinicalDetail).filter(
            AppointmentClinicalDetail.appointment_id == appointment.appointment_id
        ).first()
        if appointment_detail is None:
            appointment_detail = AppointmentClinicalDetail(
                appointment_id=appointment.appointment_id
            )
            db.add(appointment_detail)
        appointment_detail.provider_name = data.pop("provider_name")
    if "facility_id" in data:
        facility = db.query(Facility).filter(
            Facility.facility_id == data["facility_id"]
        ).first()
        if facility is None:
            raise HTTPException(status_code=404, detail="Facility was not found.")
    for field, value in data.items():
        setattr(appointment, field, value)
    db.commit()
    db.refresh(appointment)
    facility = db.query(Facility).filter(
        Facility.facility_id == appointment.facility_id
    ).first()
    detail = db.query(AppointmentClinicalDetail).filter(
        AppointmentClinicalDetail.appointment_id == appointment.appointment_id
    ).first()
    return _appointment_response(appointment, facility, detail)


@router.get("/messages")
def list_messages(
    patient_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "patient":
        patient = _patient_for_user(db, current_user)
        if patient_id is not None and patient_id != patient.patient_id:
            raise HTTPException(status_code=403, detail="You cannot access this patient.")
        peer = db.query(PatientProfile).filter(
            PatientProfile.patient_id == patient.patient_id
        ).first()
        nurse = db.query(Nurse).filter(
            Nurse.nurse_id == peer.assigned_nurse_id
        ).first() if peer and peer.assigned_nurse_id else None
        peer_user_id = nurse.user_id if nurse else None
        query = db.query(Message).filter(
            ((Message.sender_id == current_user.user_id) |
             (Message.receiver_id == current_user.user_id))
        )
        if peer_user_id is not None:
            query = query.filter(
                ((Message.sender_id == current_user.user_id) &
                 (Message.receiver_id == peer_user_id)) |
                ((Message.sender_id == peer_user_id) &
                 (Message.receiver_id == current_user.user_id))
            )
    else:
        if current_user.role == "nurse":
            nurse = _nurse_for_user(db, current_user)
            if patient_id is None:
                raise HTTPException(
                    status_code=422,
                    detail="patientId is required for nurse message history.",
                )
            patient = _accessible_patient(db, patient_id, current_user)
        else:
            if patient_id is None:
                raise HTTPException(status_code=422, detail="patientId is required.")
            patient = _accessible_patient(db, patient_id, current_user)
            nurse = None
        query = db.query(Message).filter(
            (Message.sender_id == patient.user_id)
            | (Message.receiver_id == patient.user_id)
        )
        if current_user.role == "nurse":
            query = query.filter(
                (Message.sender_id == current_user.user_id)
                | (Message.receiver_id == current_user.user_id)
            )
    messages = query.order_by(Message.sent_at).all()
    result = []
    for message in messages:
        sender = db.query(User).filter(User.user_id == message.sender_id).first()
        detail = db.query(MessageClinicalDetail).filter(
            MessageClinicalDetail.message_id == message.message_id
        ).first()
        result.append({
            "id": f"msg-{message.message_id}",
            "senderId": str(message.sender_id),
            "senderName": sender.username if sender else "MAMA+ user",
            "senderRole": (
                "mother" if sender and sender.role == "patient"
                else sender.role if sender else "system"
            ),
            "content": message.message_content,
            "timestamp": message.sent_at.isoformat() if message.sent_at else "",
            "isUrgent": detail.is_urgent if detail else False,
            "isAudio": detail.is_audio if detail else False,
            "audioDuration": detail.audio_duration if detail else None,
            "read": message.is_read,
        })
    return result


@router.post("/messages", status_code=status.HTTP_201_CREATED)
def send_message(
    message_data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "patient":
        patient = _patient_for_user(db, current_user)
        profile = _profile_for_patient(db, patient.patient_id)
        nurse = db.query(Nurse).filter(
            Nurse.nurse_id == profile.assigned_nurse_id
        ).first() if profile.assigned_nurse_id else None
        if nurse is None:
            raise HTTPException(
                status_code=409,
                detail="A nurse must be assigned before secure messaging is available.",
            )
        receiver_id = nurse.user_id
    elif current_user.role == "nurse":
        if message_data.patient_id is None:
            raise HTTPException(status_code=422, detail="patientId is required.")
        patient = _accessible_patient(db, message_data.patient_id, current_user)
        receiver_id = patient.user_id
    else:
        raise HTTPException(status_code=403, detail="Patient or nurse account required.")

    message = Message(
        sender_id=current_user.user_id,
        receiver_id=receiver_id,
        message_content=message_data.content,
    )
    db.add(message)
    db.flush()
    db.add(MessageClinicalDetail(
        message_id=message.message_id,
        is_urgent=message_data.is_urgent,
        is_audio=message_data.is_audio,
        audio_duration=message_data.audio_duration,
    ))
    if message_data.is_urgent:
        db.add(NurseAlert(
            patient_id=patient.patient_id,
            nurse_id=(
                db.query(PatientProfile).filter(
                    PatientProfile.patient_id == patient.patient_id
                ).first().assigned_nurse_id
            ),
            alert_type="support_request",
            urgency="high",
            message=message_data.content[:500],
        ))
    db.commit()
    db.refresh(message)
    return {
        "id": f"msg-{message.message_id}",
        "senderId": str(message.sender_id),
        "senderName": current_user.username,
        "senderRole": "mother" if current_user.role == "patient" else current_user.role,
        "content": message.message_content,
        "timestamp": message.sent_at.isoformat() if message.sent_at else "",
        "isUrgent": message_data.is_urgent,
        "isAudio": message_data.is_audio,
        "audioDuration": message_data.audio_duration,
        "read": False,
    }


@router.patch("/messages/{message_id}/read")
def mark_message_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = db.query(Message).filter(Message.message_id == message_id).first()
    if message is None:
        raise HTTPException(status_code=404, detail="Message was not found.")
    if message.receiver_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Only the recipient can mark this read.")
    message.is_read = True
    db.commit()
    return {"message": "Message marked as read."}


@router.get("/medications")
def list_medications(
    patient_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Medication).filter(Medication.is_active.is_(True))
    if current_user.role == "patient":
        patient = _patient_for_user(db, current_user)
        if patient_id is not None and patient_id != patient.patient_id:
            raise HTTPException(status_code=403, detail="You cannot access this patient.")
        query = query.filter(Medication.patient_id == patient.patient_id)
    elif patient_id is not None:
        _accessible_patient(db, patient_id, current_user)
        query = query.filter(Medication.patient_id == patient_id)
    elif current_user.role == "nurse":
        nurse = _nurse_for_user(db, current_user)
        assigned_patient_ids = [
            row.patient_id for row in db.query(PatientProfile.patient_id).filter(
                PatientProfile.assigned_nurse_id == nurse.nurse_id
            ).all()
        ]
        if not assigned_patient_ids:
            return []
        query = query.filter(Medication.patient_id.in_(assigned_patient_ids))
    elif current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Clinical staff access required.")

    return [
        _medication_response(item)
        for item in query.order_by(Medication.medication_id).all()
    ]


@router.post("/patients/{patient_id}/medications", status_code=status.HTTP_201_CREATED)
def assign_medication(
    patient_id: int,
    medication_data: MedicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"nurse", "admin"}:
        raise HTTPException(status_code=403, detail="Clinical staff access required.")
    patient = _accessible_patient(db, patient_id, current_user)
    values = medication_data.model_dump()
    medication = Medication(
        patient_id=patient.patient_id,
        **values,
        doses_taken=[False] * len(values["time_of_day"]),
        dose_log_date=date.today(),
    )
    db.add(medication)
    db.commit()
    db.refresh(medication)
    return _medication_response(medication)


@router.patch("/medications/{medication_id}")
def update_medication(
    medication_id: int,
    updates: MedicationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in {"nurse", "admin"}:
        raise HTTPException(status_code=403, detail="Clinical staff access required.")
    medication = db.query(Medication).filter(
        Medication.medication_id == medication_id,
        Medication.is_active.is_(True),
    ).first()
    if medication is None:
        raise HTTPException(status_code=404, detail="Medication was not found.")
    _accessible_patient(db, medication.patient_id, current_user)
    values = updates.model_dump(exclude_unset=True)
    if not values:
        raise HTTPException(status_code=422, detail="Provide at least one medication field to update.")
    schedule_changed = "time_of_day" in values and values["time_of_day"] != medication.time_of_day
    for field, value in values.items():
        setattr(medication, field, value)
    if schedule_changed:
        medication.doses_taken = [False] * len(medication.time_of_day or [])
        medication.dose_log_date = date.today()
    db.commit()
    db.refresh(medication)
    return _medication_response(medication)


@router.patch("/medications/{medication_id}/dose")
def update_medication_dose(
    medication_id: int,
    update: MedicationDoseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    medication = db.query(Medication).filter(
        Medication.medication_id == medication_id,
        Medication.is_active.is_(True),
    ).first()
    if medication is None:
        raise HTTPException(status_code=404, detail="Medication was not found.")
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Only the patient can update dose adherence.")
    patient = _patient_for_user(db, current_user)
    if medication.patient_id != patient.patient_id:
        raise HTTPException(status_code=403, detail="You cannot update this medication.")
    doses = list(medication.doses_taken or [])
    if medication.dose_log_date != date.today():
        doses = [False] * len(medication.time_of_day or [])
        medication.streak_days = 0
        medication.dose_log_date = date.today()
    if update.dose_index >= len(doses):
        raise HTTPException(status_code=422, detail="Dose index is outside the schedule.")
    previous = doses[update.dose_index]
    doses[update.dose_index] = update.taken
    medication.doses_taken = doses
    if update.taken and not previous:
        medication.streak_days += 1
        medication.last_taken_date = date.today()
    elif previous and not update.taken:
        medication.streak_days = max(0, medication.streak_days - 1)
    db.commit()
    db.refresh(medication)
    return _medication_response(medication)


@router.delete("/medications/{medication_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_medication(
    medication_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    medication = db.query(Medication).filter(
        Medication.medication_id == medication_id
    ).first()
    if medication is None:
        raise HTTPException(status_code=404, detail="Medication was not found.")
    if current_user.role not in {"nurse", "admin"}:
        raise HTTPException(status_code=403, detail="Clinical staff access required.")
    _accessible_patient(db, medication.patient_id, current_user)
    medication.is_active = False
    db.commit()


@router.get("/alerts")
def list_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "patient":
        patient = _patient_for_user(db, current_user)
        query = db.query(NurseAlert).filter(NurseAlert.patient_id == patient.patient_id)
    elif current_user.role == "nurse":
        nurse = _nurse_for_user(db, current_user)
        query = db.query(NurseAlert).filter(NurseAlert.nurse_id == nurse.nurse_id)
    else:
        query = db.query(NurseAlert)
    alerts = query.order_by(NurseAlert.created_at.desc()).all()
    result = []
    for alert in alerts:
        response = _alert_response(alert)
        patient = db.query(Patient).filter(
            Patient.patient_id == alert.patient_id
        ).first()
        account = db.query(User).filter(
            User.user_id == patient.user_id
        ).first() if patient else None
        profile = _profile_for_patient(db, alert.patient_id)
        response["patientName"] = (
            f"{account.username} (Wk {profile.gestation_week})"
            if account and profile.gestation_week else account.username if account else ""
        )
        result.append(response)
    return result


@router.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: int,
    updates: AlertUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = db.query(NurseAlert).filter(NurseAlert.alert_id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert was not found.")
    if current_user.role == "patient":
        patient = _patient_for_user(db, current_user)
        if patient.patient_id != alert.patient_id:
            raise HTTPException(status_code=403, detail="You cannot access this alert.")
    else:
        _accessible_patient(db, alert.patient_id, current_user)
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(alert, field, value)
    db.commit()
    db.refresh(alert)
    return _alert_response(alert)


@router.post("/emergency-alerts", status_code=status.HTTP_201_CREATED)
def create_emergency_alert(
    alert_data: EmergencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient account required.")
    patient = _patient_for_user(db, current_user)
    profile = _profile_for_patient(db, patient.patient_id)
    emergency = EmergencyAlert(
        patient_id=patient.patient_id,
        notes=alert_data.notes,
    )
    db.add(emergency)
    db.add(NurseAlert(
        patient_id=patient.patient_id,
        nurse_id=profile.assigned_nurse_id,
        alert_type="red_flag_symptom",
        urgency="high",
        message=alert_data.notes or "Patient activated the emergency SOS alert.",
    ))
    profile.risk_status = "high"
    db.commit()
    db.refresh(emergency)
    return {
        "id": emergency.emergency_alert_id,
        "patientId": patient.patient_id,
        "status": emergency.status,
        "notes": emergency.notes,
        "createdAt": emergency.created_at.isoformat() if emergency.created_at else "",
    }


@router.post("/kick-sessions", status_code=status.HTTP_201_CREATED)
def create_kick_session(
    session_data: KickSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient account required.")
    patient = _patient_for_user(db, current_user)
    session = KickSession(patient_id=patient.patient_id, **session_data.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "id": f"kick-{session.kick_session_id}",
        "date": session.session_date.isoformat(),
        "startTime": session.start_time,
        "durationMinutes": session.duration_minutes,
        "kickCount": session.kick_count,
        "notes": session.notes,
    }


@router.get("/kick-sessions")
def list_kick_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient account required.")
    patient = _patient_for_user(db, current_user)
    return [
        {
            "id": f"kick-{row.kick_session_id}",
            "date": row.session_date.isoformat(),
            "startTime": row.start_time,
            "durationMinutes": row.duration_minutes,
            "kickCount": row.kick_count,
            "notes": row.notes,
        }
        for row in db.query(KickSession).filter(
            KickSession.patient_id == patient.patient_id
        ).order_by(KickSession.session_date.desc()).all()
    ]


@router.post("/contractions", status_code=status.HTTP_201_CREATED)
def create_contraction(
    contraction_data: ContractionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient account required.")
    patient = _patient_for_user(db, current_user)
    contraction = ContractionLog(
        patient_id=patient.patient_id,
        start_time=datetime.now(timezone.utc),
        **contraction_data.model_dump(),
    )
    db.add(contraction)
    db.commit()
    db.refresh(contraction)
    return {
        "id": f"cnt-{contraction.contraction_log_id}",
        "startTime": contraction.start_time.isoformat(),
        "durationSeconds": contraction.duration_seconds,
        "intervalMinutes": contraction.interval_minutes,
        "intensity": contraction.intensity,
    }


@router.get("/contractions")
def list_contractions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "patient":
        raise HTTPException(status_code=403, detail="Patient account required.")
    patient = _patient_for_user(db, current_user)
    return [
        {
            "id": f"cnt-{row.contraction_log_id}",
            "startTime": row.start_time.isoformat(),
            "durationSeconds": row.duration_seconds,
            "intervalMinutes": row.interval_minutes,
            "intensity": row.intensity,
        }
        for row in db.query(ContractionLog).filter(
            ContractionLog.patient_id == patient.patient_id
        ).order_by(ContractionLog.start_time.desc()).all()
    ]


@router.get("/facilities")
def list_facilities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.query(Facility).order_by(Facility.facility_name).all()
    return [
        {
            "id": f"facility-{row.facility_id}",
            "name": row.facility_name,
            "distanceKm": detail.distance_km if detail else 0,
            "estimatedDriveTimeMins": (
                detail.estimated_drive_time_mins if detail else 0
            ),
            "emergencyHotline": (
                detail.emergency_hotline if detail else row.phone_number or ""
            ),
            "address": row.address or "",
            "maternityBedsAvailable": (
                detail.maternity_beds_available if detail else 0
            ),
            "hasNicUnit": detail.has_nic_unit if detail else False,
            "open24Hours": detail.open_24_hours if detail else False,
            "district": row.district or "",
        }
        for row in rows
        for detail in [db.query(FacilityServiceDetail).filter(
            FacilityServiceDetail.facility_id == row.facility_id
        ).first()]
    ]


@router.post("/facilities", status_code=status.HTTP_201_CREATED)
def create_facility(
    facility_data: FacilityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    facility = Facility(
        facility_name=facility_data.name.strip(),
        facility_type=facility_data.facility_type,
        address=facility_data.address,
        district=facility_data.district,
        phone_number=facility_data.phone,
        email=facility_data.email,
    )
    db.add(facility)
    db.flush()
    service_detail = FacilityServiceDetail(
        facility_id=facility.facility_id,
        distance_km=facility_data.distance_km,
        estimated_drive_time_mins=facility_data.estimated_drive_time_mins,
        emergency_hotline=facility_data.emergency_hotline,
        maternity_beds_available=facility_data.maternity_beds_available,
        has_nic_unit=facility_data.has_nic_unit,
        open_24_hours=facility_data.open_24_hours,
    )
    db.add(service_detail)
    db.commit()
    db.refresh(facility)
    return {"id": f"facility-{facility.facility_id}", "name": facility.facility_name}


@router.patch("/facilities/{facility_id}")
def update_facility(
    facility_id: int,
    updates: FacilityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    facility = db.query(Facility).filter(
        Facility.facility_id == facility_id
    ).first()
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility was not found.")
    values = updates.model_dump(exclude_unset=True)
    for source, target in (
        ("name", "facility_name"),
        ("facility_type", "facility_type"),
        ("address", "address"),
        ("district", "district"),
        ("phone", "phone_number"),
        ("email", "email"),
    ):
        if source in values:
            setattr(facility, target, values[source])
    service_fields = {
        "distance_km": "distance_km",
        "estimated_drive_time_mins": "estimated_drive_time_mins",
        "emergency_hotline": "emergency_hotline",
        "maternity_beds_available": "maternity_beds_available",
        "has_nic_unit": "has_nic_unit",
        "open_24_hours": "open_24_hours",
    }
    service_detail = db.query(FacilityServiceDetail).filter(
        FacilityServiceDetail.facility_id == facility_id
    ).first()
    if service_detail is None:
        service_detail = FacilityServiceDetail(facility_id=facility_id)
        db.add(service_detail)
    for field in service_fields:
        if field in values:
            setattr(service_detail, field, values[field])
    db.commit()
    db.refresh(facility)
    db.refresh(service_detail)
    return {
        "id": f"facility-{facility.facility_id}",
        "name": facility.facility_name,
        "distanceKm": service_detail.distance_km,
        "estimatedDriveTimeMins": service_detail.estimated_drive_time_mins,
        "emergencyHotline": service_detail.emergency_hotline,
        "address": facility.address or "",
        "maternityBedsAvailable": service_detail.maternity_beds_available,
        "hasNicUnit": service_detail.has_nic_unit,
        "open24Hours": service_detail.open_24_hours,
        "district": facility.district or "",
    }


@router.get("/articles")
def list_articles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [
        _article_response(article)
        for article in db.query(EducationalArticleRecord).order_by(
            EducationalArticleRecord.created_at.desc()
        ).all()
    ]


@router.post("/articles", status_code=status.HTTP_201_CREATED)
def create_article(
    article_data: ArticleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    article = EducationalArticleRecord(**article_data.model_dump())
    db.add(article)
    db.commit()
    db.refresh(article)
    return _article_response(article)


@router.patch("/articles/{article_id}")
def update_article(
    article_id: int,
    article_data: ArticleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    article = db.query(EducationalArticleRecord).filter(
        EducationalArticleRecord.article_id == article_id
    ).first()
    if article is None:
        raise HTTPException(status_code=404, detail="Article was not found.")
    for field, value in article_data.model_dump(exclude_unset=True).items():
        setattr(article, field, value)
    db.commit()
    db.refresh(article)
    return _article_response(article)


@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    article = db.query(EducationalArticleRecord).filter(
        EducationalArticleRecord.article_id == article_id
    ).first()
    if article is None:
        raise HTTPException(status_code=404, detail="Article was not found.")
    db.delete(article)
    db.commit()


@router.get("/admin/knowledge-rules")
def list_knowledge_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return [
        {
            "id": f"rule-{rule.rule_id}",
            "category": rule.category,
            "title": rule.title,
            "guideline": rule.guideline,
            "evidenceSource": rule.evidence_source,
            "isActive": rule.is_active,
            "isRedFlagTrigger": rule.is_red_flag_trigger,
            "updatedAt": rule.updated_at.isoformat() if rule.updated_at else "",
        }
        for rule in db.query(AiKnowledgeRuleRecord).order_by(
            AiKnowledgeRuleRecord.updated_at.desc()
        ).all()
    ]


@router.post("/admin/knowledge-rules", status_code=status.HTTP_201_CREATED)
def create_knowledge_rule(
    rule_data: KnowledgeRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    rule = AiKnowledgeRuleRecord(**rule_data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {
        "id": f"rule-{rule.rule_id}",
        "category": rule.category,
        "title": rule.title,
        "guideline": rule.guideline,
        "evidenceSource": rule.evidence_source,
        "isActive": rule.is_active,
        "isRedFlagTrigger": rule.is_red_flag_trigger,
        "updatedAt": rule.updated_at.isoformat() if rule.updated_at else "",
    }


@router.patch("/admin/knowledge-rules/{rule_id}")
def update_knowledge_rule(
    rule_id: int,
    updates: KnowledgeRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    rule = db.query(AiKnowledgeRuleRecord).filter(
        AiKnowledgeRuleRecord.rule_id == rule_id
    ).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Knowledge rule was not found.")
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)
    return {
        "id": f"rule-{rule.rule_id}",
        "category": rule.category,
        "title": rule.title,
        "guideline": rule.guideline,
        "evidenceSource": rule.evidence_source,
        "isActive": rule.is_active,
        "isRedFlagTrigger": rule.is_red_flag_trigger,
        "updatedAt": rule.updated_at.isoformat() if rule.updated_at else "",
    }


@router.post("/ai-audits", status_code=status.HTTP_201_CREATED)
def create_ai_audit(
    audit_data: AiAuditCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    audit = AiAuditRecord(
        user_id=current_user.user_id,
        **audit_data.model_dump(),
        status="flagged" if audit_data.red_flag_detected else "safe",
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return {
        "id": f"audit-{audit.audit_id}",
        "timestamp": audit.created_at.isoformat() if audit.created_at else "",
        "motherId": str(audit.user_id),
        "motherName": current_user.username,
        "gestationWeek": audit.gestation_week,
        "prompt": audit.prompt,
        "aiResponseSummary": audit.response_summary,
        "nonDiagnosticScore": audit.non_diagnostic_score,
        "redFlagDetected": audit.red_flag_detected,
        "status": audit.status,
    }


@router.get("/admin/ai-audits")
def list_ai_audits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    result = []
    for audit in db.query(AiAuditRecord).order_by(
        AiAuditRecord.created_at.desc()
    ).all():
        user = db.query(User).filter(User.user_id == audit.user_id).first()
        result.append({
            "id": f"audit-{audit.audit_id}",
            "timestamp": audit.created_at.isoformat() if audit.created_at else "",
            "motherId": str(audit.user_id),
            "motherName": user.username if user else "",
            "gestationWeek": audit.gestation_week,
            "prompt": audit.prompt,
            "aiResponseSummary": audit.response_summary,
            "nonDiagnosticScore": audit.non_diagnostic_score,
            "redFlagDetected": audit.red_flag_detected,
            "status": audit.status,
        })
    return result


@router.patch("/admin/ai-audits/{audit_id}")
def update_ai_audit(
    audit_id: int,
    updates: AiAuditUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    audit = db.query(AiAuditRecord).filter(
        AiAuditRecord.audit_id == audit_id
    ).first()
    if audit is None:
        raise HTTPException(status_code=404, detail="AI audit record was not found.")
    audit.status = updates.status
    audit.reviewed_by = current_user.user_id
    audit.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": f"audit-{audit.audit_id}", "status": audit.status}


@router.post("/system/activity", status_code=status.HTTP_201_CREATED)
def create_system_activity(
    activity_data: SystemActivityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    activity = SystemActivityRecord(
        user_id=current_user.user_id,
        action_type=activity_data.action_type,
        description=activity_data.description,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return {
        "id": f"act-{activity.activity_id}",
        "timestamp": activity.created_at.isoformat() if activity.created_at else "",
        "userId": str(current_user.user_id),
        "userName": current_user.username,
        "userRole": "mother" if current_user.role == "patient" else current_user.role,
        "actionType": activity.action_type,
        "description": activity.description,
    }


@router.get("/admin/activity")
def list_system_activity(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    rows = db.query(SystemActivityRecord).order_by(
        SystemActivityRecord.created_at.desc()
    ).limit(limit).all()
    result = []
    for activity in rows:
        user = db.query(User).filter(User.user_id == activity.user_id).first()
        result.append({
            "id": f"act-{activity.activity_id}",
            "timestamp": activity.created_at.isoformat() if activity.created_at else "",
            "userId": str(activity.user_id),
            "userName": user.username if user else "",
            "userRole": (
                "mother" if user and user.role == "patient"
                else user.role if user else "mother"
            ),
            "actionType": activity.action_type,
            "description": activity.description,
        })
    return result


@router.post("/admin/reports", status_code=status.HTTP_201_CREATED)
def create_admin_report(
    report_data: AdminReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    total_mothers = db.query(Patient).count()
    high_risk_count = db.query(PatientProfile).filter(
        PatientProfile.risk_status == "high"
    ).count()
    total_appointments = db.query(Appointment).count()
    symptom_count = db.query(SymptomLog).count()
    audits = db.query(AiAuditRecord).all()
    doses = db.query(Medication).filter(Medication.is_active.is_(True)).all()
    due_doses = [
        taken for medication in doses
        if medication.dose_log_date == date.today()
        for taken in (medication.doses_taken or [])
    ]
    adherence_rate = (
        round(sum(due_doses) / len(due_doses) * 100, 1)
        if due_doses else 0
    )
    safety_score = (
        round(sum(item.non_diagnostic_score for item in audits) / len(audits), 1)
        if audits else 0
    )
    metrics = {
        "totalMothers": total_mothers,
        "highRiskCount": high_risk_count,
        "totalAppointments": total_appointments,
        "symptomsLogged": symptom_count,
        "averageResponseTimeMinutes": 0,
        "medicationAdherenceRate": adherence_rate,
        "aiQueriesAuditCount": len(audits),
        "safetyScore": safety_score,
    }
    report = AdminReportRecord(
        title=report_data.title,
        period=report_data.period,
        metrics=metrics,
        created_by=current_user.user_id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {
        "id": f"rep-{report.report_id}",
        "title": report.title,
        "generatedAt": report.created_at.isoformat() if report.created_at else "",
        "period": report.period,
        **report.metrics,
    }


@router.get("/admin/reports")
def list_admin_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return [
        {
            "id": f"rep-{report.report_id}",
            "title": report.title,
            "generatedAt": report.created_at.isoformat() if report.created_at else "",
            "period": report.period,
            **report.metrics,
        }
        for report in db.query(AdminReportRecord).order_by(
            AdminReportRecord.created_at.desc()
        ).all()
    ]
