import os
import ssl
from uuid import uuid4
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, select
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from dotenv import load_dotenv

from app.services.llm_client import query_together
from app.services.send_email import send_email

# === LOAD ENV ===
load_dotenv()  # assumes .env in root or current dir

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "supersecret")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not found in environment!")

# === Prepare DB URL with asyncpg driver for SQLAlchemy engine ===
# IMPORTANT: The DATABASE_URL from env SHOULD NOT have '+asyncpg',
# so we add it here for the async engine only.
if DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
else:
    ASYNC_DATABASE_URL = DATABASE_URL  # fallback, but usually should start with postgresql://

# === SSL CONTEXT SETUP ===
ssl_context = ssl.create_default_context()
# If your DB requires no hostname verification, uncomment below (not recommended):
# ssl_context.check_hostname = False

# === DATABASE ENGINE & SESSION ===
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"ssl": ssl_context},
)

SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# === FASTAPI APP ===
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# === MODELS ===
class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    sender = Column(String)
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    session = relationship("Session", back_populates="messages")

# === LOAD CONTEXT FILE ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
varun_file_path = os.path.join(BASE_DIR, "varun_data.txt")

if not os.path.exists(varun_file_path):
    raise RuntimeError(f"❌ 'varun_data.txt' not found at {varun_file_path}")
with open(varun_file_path, "r", encoding="utf-8") as f:
    varun_context = f.read()

# === SCHEMAS ===
class ChatMessage(BaseModel):
    message: str
    session_id: str | None = None

class AdminAuth(BaseModel):
    secret: str

# === DB DEPENDENCY ===
async def get_db():
    async with SessionLocal() as session:
        yield session

# === ROUTES ===
@app.post("/chat")
async def chat(msg: ChatMessage, db: AsyncSession = Depends(get_db)):
    question = msg.message.strip()
    if not question:
        raise HTTPException(status_code=400, detail="❌ Please ask a valid question.")
    if len(question.split()) > 60:
        raise HTTPException(status_code=400, detail="❌ Please keep your question within 60 words.")

    session_id = msg.session_id or str(uuid4())
    session_obj = await db.get(Session, session_id)
    if not session_obj:
        session_obj = Session(id=session_id)
        db.add(session_obj)
        await db.commit()

    prompt = f"""
You are a helpful AI assistant who answers ONLY questions about Varun Gandhi.

Here is all the information you know:
\"\"\"
{varun_context}
\"\"\"

Answer this question in a friendly, natural tone:
\"{question}\"
"""
    try:
        result = await query_together(prompt)
    except Exception as e:
        print("❌ ERROR:", str(e))
        result = "⚠️ Failed to get a response from the AI. Try again later."

    db.add_all([
        Message(session_id=session_id, sender="user", content=question),
        Message(session_id=session_id, sender="bot", content=result)
    ])
    await db.commit()

    return {"response": f"🤖 {result}", "session_id": session_id}

@app.post("/admin/history")
async def admin_history(auth: AdminAuth, db: AsyncSession = Depends(get_db)):
    if auth.secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="❌ Unauthorized")

    sessions = await db.execute(select(Session).order_by(Session.created_at.desc()))
    session_objs = sessions.scalars().all()

    return {
        "sessions": [
            {
                "session_id": s.id,
                "created_at": s.created_at.isoformat(),
                "messages": [
                    {"from": m.sender, "text": m.content, "timestamp": m.timestamp.isoformat()}
                    for m in s.messages
                ]
            }
            for s in session_objs
        ]
    }

@app.post("/send-feedback")
async def send_feedback(data: dict = Body(...)):
    subject = "New Contact Form Submission" if data.get("type") == "contact" else "New Issue Report"
    body = "\n".join(f"{key.capitalize()}: {val}" for key, val in data.items())

    if not send_email(subject, body):
        raise HTTPException(status_code=500, detail="Failed to send email")

    return {"message": "Email sent successfully"}

# === STARTUP EVENT ===
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
