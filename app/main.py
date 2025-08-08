from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from llm_client import query_together
from uuid import uuid4
from datetime import datetime
from fastapi import Body
import os
from dotenv import load_dotenv
from send_email import send_email

app = FastAPI()

# === ENV + DB SETUP ===
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "supersecret")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not found in environment!")

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# === MODELS ===
class Session(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    messages = relationship("Message", back_populates="session")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    sender = Column(String)  # 'user' or 'bot'
    content = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    session = relationship("Session", back_populates="messages")

# === APP SETUP ===

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load context about Varun
try:
    with open("varun_data.txt", "r", encoding="utf-8") as f:
        varun_context = f.read()
except FileNotFoundError:
    raise RuntimeError("❌ 'varun_data.txt' not found in backend folder.")

# === SCHEMAS ===
class ChatMessage(BaseModel):
    message: str
    session_id: str | None = None

class AdminAuth(BaseModel):
    secret: str

# === UTILS ===
async def get_db():
    async with SessionLocal() as session:
        yield session

# === ROUTES ===
@app.post("/chat")
async def chat(msg: ChatMessage, db: AsyncSession = Depends(get_db)):
    question = msg.message.strip()
    word_count = len(question.split())

    if not question:
        raise HTTPException(status_code=400, detail="❌ Please ask a valid question.")

    if word_count > 60:
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

    return {
        "response": "🤖 " + result,
        "session_id": session_id
    }

@app.post("/admin/history")
async def admin_history(auth: AdminAuth, db: AsyncSession = Depends(get_db)):
    if auth.secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="❌ Unauthorized")

    sessions = await db.execute(select(Session).order_by(Session.created_at.desc()))
    session_objs = sessions.scalars().all()

    full_data = []
    for session in session_objs:
        session_data = {
            "session_id": session.id,
            "created_at": session.created_at.isoformat(),
            "messages": [
                {
                    "from": msg.sender,
                    "text": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                }
                for msg in session.messages
            ],
        }
        full_data.append(session_data)

    return {"sessions": full_data}

@app.post("/send-feedback")
async def send_feedback(data: dict = Body(...)):
    subject = "New Contact Form Submission" if data.get("type") == "contact" else "New Issue Report"
    lines = [f"{key.capitalize()}: {val}" for key, val in data.items()]
    body = "\n".join(lines)
    
    success = send_email(subject, body)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send email")

    return {"message": "Email sent successfully"}

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
