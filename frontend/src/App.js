import React, { useEffect, useRef, useState } from "react";
import "./App.css";

// Prefer Render env var (Static Site), fallback to optional index.html injection, then localhost
const API_BASE =
  process.env.REACT_APP_API_BASE ||
  (typeof window !== "undefined" && window.__API_BASE) ||
  "https://ellie-backend-7o2d.onrender.com";

// persistent user id so Ellie remembers you
function getUserId() {
  const k = "ellie_user_id";
  let id = localStorage.getItem(k);
  if (!id) {
    id = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
    localStorage.setItem(k, id);
  }
  return id;
}
const USER_ID = getUserId();

export default function App() {
  const [messages, setMessages] = useState([]); // {sender: "ai"|"user", text: string}
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState(null);
  const scroller = useRef(null);

  // load history on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/history/${encodeURIComponent(USER_ID)}`);
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const data = await res.json();
        if (Array.isArray(data.messages) && data.messages.length) {
          setMessages(data.messages);
        } else {
          setMessages([{ sender: "ai", text: "Hiii 💕 I’m Ellie. How’s your heart today?" }]);
        }
      } catch {
        setMessages([{ sender: "ai", text: "Hiii 💕 I’m Ellie. How’s your heart today?" }]);
      }
    })();
  }, []);

  // autoscroll
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [messages, isTyping]);

  async function sendMessage() {
    const text = input.trim();
    if (!text) return;

    setMessages((m) => [...m, { sender: "user", text }]);
    setInput("");
    setIsTyping(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userId: USER_ID, message: text }),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `${res.status} ${res.statusText}`);

      setMessages((m) => [...m, { sender: "ai", text: data.reply }]);
    } catch (e) {
      setError(e.message || "Failed to reach backend");
      setMessages((m) => [
        ...m,
        { sender: "ai", text: "Aww, I’m having trouble connecting right now 😢 Try again?" },
      ]);
    } finally {
      setIsTyping(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  async function resetHistory() {
    await fetch(`${API_BASE}/api/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId: USER_ID }),
    });
    setMessages([{ sender: "ai", text: "Fresh start! Tell me something cute ✨" }]);
  }

  async function saveProfile() {
    await fetch(`${API_BASE}/api/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId: USER_ID, name: "Shon", preferences: "coffee, gaming" }),
    });
    alert("Saved! I’ll keep it in mind ☕🎮");
  }

  return (
    <div className="page">
      <div className="chat-card">
        <div className="chat-header">
          <img
            src="/avatar-girl.png"
            alt="Ellie"
            className="avatar"
            onError={(e) => (e.currentTarget.style.display = "none")}
          />
          <div className="title-block">
            <h1 className="title">Ellie</h1>
            <div className="subtitle">fierce, nerdy, supportive & sparkly</div>
          </div>
          <div className="header-actions">
            <button className="btn ghost" onClick={saveProfile}>Save Profile</button>
            <button className="btn danger" onClick={resetHistory}>Reset</button>
          </div>
        </div>

        <div ref={scroller} className="messages">
          {messages.map((m, i) => (
            <Message key={i} sender={m.sender} text={m.text} />
          ))}
          {isTyping && (
            <div className="bubble ai typing">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          )}
        </div>

        <div className="input-row">
          <textarea
            className="input"
            placeholder="Type something sweet…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            rows={2}
          />
          <button className="btn primary" onClick={sendMessage}>Send</button>
        </div>

        {error && <div className="error">Error: {error}</div>}
      </div>
    </div>
  );
}

function Message({ sender, text }) {
  const isAI = sender === "ai";
  return (
    <div className={`row ${isAI ? "left" : "right"}`}>
      {isAI && (
        <img
          src="/avatar-girl.png"
          alt=""
          className="bubble-avatar"
          onError={(e) => e.currentTarget.remove()}
        />
      )}
      <div className={`bubble ${isAI ? "ai" : "me"}`}>{text}</div>
      {!isAI && <div className="bubble-avatar me-avatar">🫶</div>}
    </div>
  );
}
