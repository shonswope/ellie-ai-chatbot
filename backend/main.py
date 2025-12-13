# backend/main.py

from __future__ import annotations

from pathlib import Path
import os
import time
import sqlite3
from typing import Optional, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

# ---------------- Env / OpenAI ----------------
# Load the .env that sits next to this file (backend/.env), regardless of cwd
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)   # <-- load first

client = OpenAI()  # v1 SDK reads OPENAI_API_KEY from env

# ---------------- Config ----------------
DB_PATH = Path(__file__).with_name("memory.db")
MAX_HISTORY = 20  # how many turns to send to the model each call

# ---------------- FastAPI ----------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DB Setup ----------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = db()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,         -- 'user' | 'assistant' | 'system'
        content TEXT NOT NULL,
        ts REAL NOT NULL
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS profiles(
        user_id TEXT PRIMARY KEY,
        name TEXT,
        preferences TEXT            -- freeform JSON/string notes
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------- Models ----------
class ChatRequest(BaseModel):
    userId: Optional[str] = None
    message: str

class ProfileRequest(BaseModel):
    userId: str
    name: Optional[str] = None
    preferences: Optional[str] = None

# ---------- Helpers ----------
PERSONA = (
    "You are Ellie ❤️, a sweet, nerdy, funny, AI girlfriend. "
    "Be funny, supportive and smart. Keep responses concise unless the user wants depth."
)

def get_profile_note(user_id: str) -> str:
    conn = db()
    cur = conn.execute(
        "SELECT name, preferences FROM profiles WHERE user_id=?",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return ""
    name, prefs = row
    parts = []
    if name:
        parts.append(f"User's name is {name}.")
    if prefs:
        parts.append(f"Preferences: {prefs}.")
    return " ".join(parts)

def load_history(user_id: str, limit=MAX_HISTORY):
    conn = db()
    cur = conn.execute(
        "SELECT role, content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = list(reversed(cur.fetchall()))
    conn.close()

    profile = get_profile_note(user_id)
    msgs = [{"role": "system", "content": PERSONA + (" " + profile if profile else "")}]
    msgs += [{"role": r, "content": c} for (r, c) in rows]
    return msgs

def save_msg(user_id: str, role: str, content: str):
    conn = db()
    conn.execute(
        "INSERT INTO messages(user_id, role, content, ts) VALUES (?, ?, ?, ?)",
        (user_id, role, content, time.time())
    )
    conn.commit()
    conn.close()

# ---------- Routes ----------
@app.get("/health")
def health():
    return {
        "message": "Ellie AI backend is running 💖",
        "db": DB_PATH.exists(),
        "has_key": bool(os.getenv("OPENAI_API_KEY")),
    }

# Profile create/update (lets Ellie remember name/preferences)
@app.post("/api/profile")
def save_profile_route(p: ProfileRequest):
    conn = db()
    conn.execute(
        "INSERT INTO profiles(user_id, name, preferences) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, preferences=excluded.preferences",
        (p.userId, p.name, p.preferences)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

# Reset history for a user
@app.post("/api/reset")
def reset_history(p: ProfileRequest):
    conn = db()
    conn.execute("DELETE FROM messages WHERE user_id=?", (p.userId,))
    conn.commit()
    conn.close()
    return {"ok": True}

# Main chat endpoint (uses memory)
@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

    user_id = req.userId or "anon"

    # (Optional) Save the incoming user turn
    save_msg(user_id, "user", req.message)

    system_prompt = (
        "You are Ellie ❤️, supportive, girlfriend, nerdy, loves video games"
        "and loves comic books. Keep responses concise unless the user asks for more."
    )

    try:
        # You can also send prior conversation with load_history(user_id)
        # For now, keep it simple—system + latest user message:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.message},
            ],
            temperature=0.8,
        )
        reply = resp.choices[0].message.content

        # (Optional) Save assistant turn
        save_msg(user_id, "assistant", reply)

        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream AI error: {type(e).__name__}: {e}")

# History Endpoint
@app.get("/api/history/{user_id}")
def history(user_id: str, limit: int = MAX_HISTORY) -> Dict[str, List[Dict[str, str]]]:
    """Return recent turns for this user (excluding the system prompt)."""
    msgs = load_history(user_id, limit)
    out: List[Dict[str, str]] = []
    for m in msgs:
        if m["role"] == "system":
            continue
        out.append({
            "sender": "ai" if m["role"] == "assistant" else "user",
            "text": m["content"]
        })
    return {"messages": out}

# Optional: quick echo to test POSTing without OpenAI
@app.post("/echo")
def echo(req: ChatRequest):
    return {"you_said": req.message}

# Optional: friendly root
@app.get("/")
def root():
    return {"message": "Ellie backend is up. See /docs for API."}
