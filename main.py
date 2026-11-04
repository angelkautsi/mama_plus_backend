from fastapi import FastAPI

app = FastAPI(
    title="MAMA+ API",
    description="AI-Enhanced maternal care companion",
    version="1.0.0",
)

@app.get("/")
def home():
    return {"message": "Welcome to the MAMA+!", "status": "API is running successfully."}