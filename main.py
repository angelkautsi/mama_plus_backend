from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.routes.users import router as users_router
from backend.routes.clinical import router as clinical_router

from database.database import get_db

app = FastAPI(
    title="MAMA+ API",
    description="AI-Enhanced maternal care companion",
    version="1.0.0",
)

#regster routes
app.include_router(users_router)
app.include_router(clinical_router)


@app.get("/")
def home():
    return {
        "message": "Welcome to MAMA+!",
        "status": "API is running successfully."
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "MAMA+ API"
    }


@app.get("/database-test")
def database_test(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))

    return {
        "message": "Database connection successful!",
        "status": "connected"
    }
