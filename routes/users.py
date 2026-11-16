
import hashlib
import logging
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database.database import get_db
from database.models import (
    PasswordResetToken,
    Patient,
    PatientProfile,
    Pregnancy,
    User,
)

from backend.schemas.users import (
    UserCreate,
    UserResponse,
    UserLogin,
    TokenResponse,
    UserUpdate,
    PasswordResetRequest,
    PasswordResetConfirm,
)

from backend.security.password import hash_password, verify_password
from backend.auth.jwt import create_access_token

from backend.auth.dependencies import get_current_user

router = APIRouter(
    prefix="/users",
    tags=["User Management"]
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
logger = logging.getLogger(__name__)


def _send_password_reset_email(email: str, token: str) -> None:
    smtp_host = os.getenv("SMTP_HOST")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset email is not configured correctly. Contact support.",
        ) from error
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM_EMAIL")
    if not smtp_host or not sender:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset email is not configured. Contact support.",
        )

    frontend_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
    reset_url = f"{frontend_url}/?reset_token={token}"
    message = EmailMessage()
    message["Subject"] = "Reset your MAMA+ password"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "A password reset was requested for your MAMA+ account.\n\n"
        f"Use this link within 30 minutes to choose a new password:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if smtp_username and smtp_password:
            smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):

    # Check whether username or email already exists
    existing_user = db.query(User).filter(
        (User.username == user_data.username) |
        (User.email == user_data.email)
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered."
        )

    # Create a new user
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        role="patient",
        is_active=True
    )

    try:
        db.add(new_user)
        db.flush()

        patient = Patient(
            user_id=new_user.user_id,
            full_name=user_data.full_name,
            phone_number=user_data.phone_number,
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
        ))
        db.add(Pregnancy(
            patient_id=patient.patient_id,
            expected_delivery_date=user_data.due_date,
        ))
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already registered."
        )

    return new_user


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    request: PasswordResetRequest,
    db: Session = Depends(get_db),
):
    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset email is not configured correctly. Contact support.",
        ) from error
    if not os.getenv("SMTP_HOST") or not os.getenv("SMTP_FROM_EMAIL") or not 1 <= smtp_port <= 65535:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset email is not configured. Contact support.",
        )
    user = db.query(User).filter(User.email == request.email).first()
    if user is None:
        return {
            "message": "If an account exists for that email, password reset instructions will be sent."
        }

    raw_token = secrets.token_urlsafe(32)
    token_record = PasswordResetToken(
        user_id=user.user_id,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.user_id,
        PasswordResetToken.used_at.is_(None),
    ).update(
        {PasswordResetToken.used_at: datetime.now(timezone.utc)},
        synchronize_session=False,
    )
    db.add(token_record)
    db.commit()
    try:
        _send_password_reset_email(request.email, raw_token)
    except (OSError, smtplib.SMTPException) as error:
        token_record.used_at = datetime.now(timezone.utc)
        db.commit()
        logger.error("Password reset email delivery failed", exc_info=True)
    return {
        "message": "If an account exists for that email, password reset instructions will be sent."
    }


@router.post("/password-reset/confirm")
def confirm_password_reset(
    request: PasswordResetConfirm,
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(request.token.encode("utf-8")).hexdigest()
    token_record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used_at.is_(None),
    ).first()
    if token_record is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired.",
        )

    now = datetime.now(timezone.utc)
    expires_at = token_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        token_record.used_at = now
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired.",
        )

    user = db.query(User).filter(User.user_id == token_record.user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired.",
        )
    user.password_hash = hash_password(request.password)
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.user_id,
        PasswordResetToken.used_at.is_(None),
    ).update(
        {PasswordResetToken.used_at: now},
        synchronize_session=False,
    )
    db.commit()
    return {"message": "Password updated. You can now sign in with your new password."}

@router.post("/login", response_model=TokenResponse)
def login_user(user_data: UserLogin, db: Session = Depends(get_db)):

    # Find user by username or email
    user = db.query(User).filter(
        (User.username == user_data.identifier) |
        (User.email == user_data.identifier)
    ).first()

    # Check whether the user exists and the password is correct
    if not user or not verify_password(
        user_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Prevent inactive accounts from logging in
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive."
        )

    # Generate an access token
    access_token = create_access_token(
        user_id=user.user_id,
        role=user.role
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user)
):
    return current_user

@router.put("/me", response_model=UserResponse)
def update_my_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check whether the new username is already in use
    if user_data.username is not None:
        existing_username = db.query(User).filter(
            User.username == user_data.username,
            User.user_id != current_user.user_id
        ).first()

        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username is already in use."
            )

        current_user.username = user_data.username

    # Check whether the new email is already in use
    if user_data.email is not None:
        existing_email = db.query(User).filter(
            User.email == user_data.email,
            User.user_id != current_user.user_id
        ).first()

        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already in use."
            )

        current_user.email = user_data.email

    try:
        db.commit()
        db.refresh(current_user)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email is already in use."
        )

    return current_user

@router.delete("/me")
def deactivate_my_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_user.is_active = False

    db.commit()

    return {
        "message": "Your account has been deactivated successfully."
    }