import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './index.css';

const API_URL = `http://${window.location.hostname}:8000`;
const generateId = () => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
};

/* ─────── Auth Screen ─────── */
function AuthScreen({ onLogin }) {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      if (isRegister) {
        if (password !== confirmPassword) throw new Error('Passwords do not match.');
        const res = await fetch(`${API_URL}/auth/register`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, username, password, confirm_password: confirmPassword }),
        });
        if (!res.ok) {
          const dat = await res.json();
          let msg = dat.detail || 'Registration failed';
          if (Array.isArray(msg)) msg = msg[0].msg.replace('Value error, ', '');
          throw new Error(msg);
        }
        setIsRegister(false); setError('Registered! Please sign in.');
      } else {
        const res = await fetch(`${API_URL}/auth/login`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
          const dat = await res.json();
          throw new Error(dat.detail || 'Invalid email or password');
        }
        onLogin((await res.json()).access_token);
      }
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-card">
        <div className="auth-logo">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L3 7V17L12 22L21 17V7L12 2Z" stroke="#c5a059" strokeWidth="2" strokeLinejoin="round"/>
            <path d="M12 22V12" stroke="#c5a059" strokeWidth="2" strokeLinecap="round"/>
            <path d="M12 12L21 7" stroke="#c5a059" strokeWidth="2" strokeLinecap="round"/>
            <path d="M12 12L3 7" stroke="#c5a059" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <span>Legal Counsel <strong>AI</strong></span>
        </div>
        <h2 className="auth-heading">{isRegister ? 'Firm Registration' : 'Counsel Access'}</h2>
        <p className="auth-sub">{isRegister ? 'Onboard your firm to the intelligence cloud' : 'Securely access your firm\'s knowledge base'}</p>
        {error && <div className={`auth-alert ${error.includes('Registered') ? 'auth-alert--ok' : ''}`}>{error}</div>}
        <form onSubmit={handleSubmit}>
          <label className="field-label">Email address</label>
          <input className="field-input" type="email" value={email} onChange={e => setEmail(e.target.value)} required placeholder="you@company.com" />
          {isRegister && <>
            <label className="field-label">Username</label>
            <input className="field-input" type="text" value={username} onChange={e => setUsername(e.target.value)} required placeholder="yourname" />
          </>}
          <label className="field-label">Password</label>
          <input className="field-input" type="password" value={password} onChange={e => setPassword(e.target.value)} required placeholder="••••••••" />
          {isRegister && <>
            <label className="field-label">Confirm password</label>
            <input className="field-input" type="password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required placeholder="••••••••" />
          </>}
          <button className="auth-submit" disabled={loading}>{loading ? 'Please wait…' : (isRegister ? 'Create account' : 'Sign in')}</button>
        </form>
        <p className="auth-switch">
          {isRegister ? 'Already have an account? ' : "Don't have an account? "}
          <button className="auth-switch-btn" onClick={() => { setIsRegister(!isRegister); setError(''); }}>
            {isRegister ? 'Sign in' : 'Sign up'}
          </button>
        </p>
      </div>
    </div>
  );
}

/* ─────── Sidebar ─────── */
function Sidebar({ sessions, activeSession, onNewChat, onSelectSession, onDeleteSession, isOpen }) {
  return (
    <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
      <div className="sb-brand">
        <div className="sb-brand-name">Legal Counsel <span>AI</span></div>
        <div className="sb-brand-sub">Firm Intelligence Node</div>
      </div>

      <button className="sb-new-btn" onClick={onNewChat}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
          <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
        New conversation
      </button>

      <div className="sb-section-label">Recent chats</div>
      <div className="sb-list">
        {sessions.length === 0 && <div className="sb-empty">No conversations yet</div>}
        {sessions.map(s => (
          <div key={s.id} className={`sb-item ${activeSession === s.id ? 'sb-item--active' : ''}`} onClick={() => onSelectSession(s.id)}>
            <svg className="sb-item-icon" width="13" height="13" viewBox="0 0 24 24" fill="none">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="currentColor" strokeWidth="1.8" />
            </svg>
            <div className="sb-item-info">
              <div className="sb-item-title">{s.title}</div>
              <div className="sb-item-meta">{s.messageCount} messages</div>
            </div>
            <button className="sb-item-del" onClick={e => { e.stopPropagation(); onDeleteSession(s.id); }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
            </button>
          </div>
        ))}
      </div>

      <div className="sb-footer">
        <div className="sb-footer-title">System</div>
        <div className="sb-status"><span className="sb-dot sb-dot--green"></span>BAAI/bge-small-en-v1.5</div>
        <div className="sb-status"><span className="sb-dot sb-dot--blue"></span>Qdrant · 5 Collections</div>
        <div className="sb-status"><span className="sb-dot sb-dot--purple"></span>Gemini 2.5 Flash</div>
      </div>
    </aside>
  );
}

/* ─────── Document reference highlighter ─────── */
function HighlightedText({ text }) {
  const refPattern = /\b(SOP-[A-Z0-9-]+|DEV-[A-Z0-9-]+|CAPA-[A-Z0-9-]+|DEC-\d{4}-\d+|FIND-\d{4}-\d+)/g;
  const parts = text.split(refPattern);
  return (
    <>
      {parts.map((part, i) =>
        refPattern.test(part)
          ? <span key={i} className="ref-pill">{part}</span>
          : part
      )}
    </>
  );
}

/* ─────── Message ─────── */
function BotMessage({ msg, onSuggestionClick }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
  };

  const allCits = (msg.citations || []).filter(c => c.ref);

  if (msg.error) {
    return (
      <div className="msg-bot">
        <div className="msg-bot-bubble msg-bot-bubble--error">{msg.text}</div>
      </div>
    );
  }

  return (
    <div className="msg-bot">
      {/* The Answer in Prose */}
      <div className="msg-bot-bubble">
        <div className="markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {msg.text}
          </ReactMarkdown>
        </div>

        {/* Citations row */}
        {allCits.length > 0 && (
          <div className="cit-row">
            <span className="cit-row-label">Sources:</span>
            {allCits.slice(0, 8).map((c, i) => (
              <span key={i} className={`cit-tag cit-tag--${(c.type || 'SOP').toLowerCase().slice(0, 3)}`} title={c.title}>
                {c.ref}
              </span>
            ))}
            {allCits.length > 8 && <span className="cit-tag cit-tag--more">+{allCits.length - 8}</span>}
          </div>
        )}

        {/* Stats */}
        {msg.retrieval_stats && (
          <div className="stats-row">
            <span className="stat-item">Searched: <strong>{msg.retrieval_stats.searched?.map(s => s.toUpperCase()).join(', ') || 'All'}</strong></span>
            <span className="stat-item">Docs Retrieved: <strong>{msg.retrieval_stats.total_docs}</strong></span>
            <span className="stat-latency">{(msg.retrieval_stats.latency_ms / 1000).toFixed(1)}s</span>
          </div>
        )}
      </div>

      {/* Dynamic suggestions AFTER each bot response */}
      {msg.suggestions && msg.suggestions.length > 0 && (
        <div className="followup-suggestions">
          <div className="followup-label">Suggestions</div>
          <div className="followup-chips">
            {msg.suggestions.map((s, i) => (
              <button key={i} className="followup-chip" onClick={() => onSuggestionClick(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function UserMessage({ msg }) {
  return (
    <div className="msg-user-row">
      <div className="msg-user-bubble">{msg.text}</div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="msg-bot">
      <div className="typing-bubble">
        <span></span><span></span><span></span>
      </div>
    </div>
  );
}

/* ─────── Profile Panel ─────── */
function ProfilePanel({ user, token, onClose, onProfileUpdated, onLogout }) {
  const [username, setUsername] = useState(user?.username || '');
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  const save = async (e) => {
    e.preventDefault(); setMsg(null);
    if (newPw && newPw !== confirmPw) { setMsg({ type: 'error', text: 'Passwords do not match.' }); return; }
    setSaving(true);
    const body = {};
    if (username.trim()) body.username = username.trim();
    if (newPw) { body.current_password = currentPw; body.new_password = newPw; }
    try {
      const res = await fetch(`${API_URL}/auth/me`, { method: 'PATCH', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify(body) });
      const dat = await res.json();
      if (!res.ok) throw new Error(Array.isArray(dat.detail) ? dat.detail[0].msg : dat.detail || 'Update failed');
      onProfileUpdated(dat); setCurrentPw(''); setNewPw(''); setConfirmPw('');
      setMsg({ type: 'ok', text: 'Profile updated!' });
    } catch (err) { setMsg({ type: 'error', text: err.message }); }
    finally { setSaving(false); }
  };

  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="profile-panel">
        <div className="pp-header">
          <h3>Firm Ledger & Identity</h3>
          <button className="pp-close" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="12" y2="12"></line><line x1="18" y1="18" x2="12" y2="12"></line></svg>
          </button>
        </div>
        <div className="pp-body">
          <div className="pp-identity-card">
            <div className="pp-avatar">{(user?.username || 'U').slice(0, 2).toUpperCase()}</div>
            <div className="pp-info-main">
              <div className="pp-name">{user?.username}</div>
              <div className="pp-email">{user?.email}</div>
              <div className="pp-role-badge">{user?.role || 'Senior Counsel'}</div>
            </div>
          </div>

          <form className="pp-form" onSubmit={save}>
            {msg && <div className={`pp-msg ${msg.type === 'ok' ? 'pp-msg--ok' : 'pp-msg--err'}`}>{msg.text}</div>}

            <div className="pp-section-title">Professional Identity</div>
            <label className="field-label">Display Name</label>
            <input className="field-input" value={username} onChange={e => setUsername(e.target.value)} placeholder="Firm designation" />
            <label className="field-label">Registered Email</label>
            <input className="field-input" value={user?.email || ''} disabled />

            <div className="pp-section-title">Access Credentials</div>
            <label className="field-label">Current Authentication</label>
            <input className="field-input" type="password" value={currentPw} onChange={e => setCurrentPw(e.target.value)} placeholder="Required for vault safety" />
            
            <label className="field-label">New Password</label>
            <input className="field-input" type="password" value={newPw} onChange={e => setNewPw(e.target.value)} placeholder="Min 8 chars, 1 uppercase" />
            
            <label className="field-label">Confirm New Password</label>
            <input className="field-input" type="password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)} />

            <div className="pp-actions">
              <button className="pp-save" type="submit" disabled={saving}>{saving ? 'Authorizing…' : 'Update Credentials'}</button>
              <button className="pp-logout" type="button" onClick={onLogout}>Revoke Access (Sign Out)</button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

/* ─────── App Root ─────── */
export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || null);
  const [user, setUser] = useState(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  const handleLogin = async (tok) => {
    localStorage.setItem('token', tok); setToken(tok);
    try { const r = await fetch(`${API_URL}/auth/me`, { headers: { Authorization: `Bearer ${tok}` } }); if (r.ok) setUser(await r.json()); } catch (_) { }
  };
  const handleLogout = () => { localStorage.removeItem('token'); setToken(null); setUser(null); };

  useEffect(() => {
    if (token && !user) {
      fetch(`${API_URL}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
        .then(r => r.ok ? r.json() : null).then(d => { if (d) setUser(d); else handleLogout(); }).catch(() => { });
    }
  }, [token]);

  const loadSessions = async (tok) => {
    try {
      const res = await fetch(`${API_URL}/chat/sessions`, { headers: { Authorization: `Bearer ${tok}` } });
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
        if (data.length > 0 && !activeSessionId) handleSelectSession(data[0].id, tok);
        if (data.length === 0) handleNewChat();
      }
    } catch (_) { }
  };

  useEffect(() => {
    if (token && user) loadSessions(token);
  }, [token, user]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, loading]);

  const handleNewChat = () => {
    const id = generateId();
    setSessions(p => [{ id, title: 'New conversation', _isTemp: true }, ...p]);
    setActiveSessionId(id); setMessages([]);
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

  const handleSelectSession = async (sid, tok = token) => {
    const s = sessions.find(x => x.id === sid);
    setActiveSessionId(sid); setMessages([]);
    if (!s?._isTemp) {
      try {
        const res = await fetch(`${API_URL}/chat/sessions/${sid}`, { headers: { Authorization: `Bearer ${tok}` } });
        if (res.ok) {
          const d = await res.json();
          setMessages(d.messages.map(m => ({
            role: m.role === 'assistant' ? 'bot' : 'user', id: m.id, text: m.content,
            citations: m.citations, suggestions: m.retrieval_metadata?.suggestions, retrieval_stats: m.retrieval_metadata?.stats
          })));
        }
      } catch (_) { }
    }
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

  const handleDeleteSession = async (sid) => {
    try {
      if (!sessions.find(s => s.id === sid)?._isTemp) {
        await fetch(`${API_URL}/chat/sessions/${sid}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
      }
    } catch (_) { }
    setSessions(prev => {
      const f = prev.filter(s => s.id !== sid);
      if (sid === activeSessionId && f.length > 0) handleSelectSession(f[0].id);
      else if (f.length === 0) handleNewChat();
      return f;
    });
  };

  const send = async (queryText) => {
    const query = (queryText || input).trim();
    if (!query || loading) return;
    const userMsg = { role: 'user', id: generateId(), text: query };
    const next = [...messages, userMsg];
    setMessages(next); setInput(''); setLoading(true);

    try {
      let qid = activeSessionId;
      // 1. Create DB session if it was a temp new chat
      if (sessions.find(s => s.id === qid)?._isTemp) {
        try {
          const sRes = await fetch(`${API_URL}/chat/sessions`, {
            method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({ title: query.substring(0, 40), collection_name: "sops" })
          });
          if (sRes.ok) {
            const sData = await sRes.json();
            qid = sData.id;
            setSessions(prev => [sData, ...prev.filter(x => x.id !== activeSessionId)]);
            setActiveSessionId(qid);
          }
        } catch (dbErr) { console.error("Session creation failed", dbErr); }
      }

      // 2. Save user message to DB (Non-blocking)
      fetch(`${API_URL}/chat/sessions/${qid}/messages`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ session_id: qid, role: 'user', content: query })
      }).catch(e => console.error("History save failed", e));

      // 3. Federated Query processing
      const resp = await fetch(`${API_URL}/query/federated`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ query }),
      });

      if (resp.status === 401) { handleLogout(); throw new Error('Session expired. Please sign in again.'); }

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({ detail: `Server error ${resp.status}` }));
        throw new Error(errData.detail || `Server error ${resp.status}`);
      }

      const data = await resp.json();

      // 4. Save bot message to DB (Non-blocking)
      fetch(`${API_URL}/chat/sessions/${qid}/messages`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ 
          session_id: qid, 
          role: 'assistant', 
          content: data.answer, 
          citations: data.citations || [], 
          retrieval_metadata: { suggestions: data.suggestions || [], stats: data.retrieval_stats },
          // Audit Vault Fields
          metadata_snapshot: data.metadata_snapshot || [],
          audit_log_snapshot: data.audit_log_snapshot || [],
          action_metadata: data.action_metadata || {}
        })
      }).catch(e => console.error("History save failed", e));

      const botMsg = {
        role: 'bot', id: generateId(), text: data.answer, suggestions: data.suggestions || [],
        citations: data.citations || [], retrieval_stats: data.retrieval_stats,
      };
      setMessages([...next, botMsg]);
    } catch (err) {
      let msg = err.message;
      if (msg === 'Failed to fetch') msg = 'Connection lost. Please check if the backend is running.';
      setMessages([...next, { role: 'bot', id: generateId(), error: true, text: `Error: ${msg}` }]);
    } finally { setLoading(false); setTimeout(() => inputRef.current?.focus(), 50); }
  };

  const handleCopyLast = () => {
    const last = [...messages].reverse().find(m => m.role === 'bot' && !m.error);
    if (!last) return;
    navigator.clipboard.writeText(last.text);
  };

  const isWelcome = messages.length === 0;
  const userInitials = (user?.username || 'U').slice(0, 2).toUpperCase();

  if (!token) return <AuthScreen onLogin={handleLogin} />;

  return (
    <div className="app">
      {profileOpen && user && (
        <ProfilePanel user={user} token={token} onClose={() => setProfileOpen(false)} onProfileUpdated={setUser} onLogout={handleLogout} />
      )}

      <Sidebar
        sessions={sessions} activeSession={activeSessionId}
        onNewChat={handleNewChat} onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession} isOpen={sidebarOpen}
      />

      <div className={`main ${sidebarOpen ? 'main--shifted' : ''}`}>
        {/* Top bar */}
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-btn" onClick={() => setSidebarOpen(p => !p)}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
            </button>
          </div>
          <div className="topbar-mid">
            <span className="topbar-ai-label">Counsel Assistant</span>
            <span className="topbar-ctx">Secure Workspace: <strong>{user?.username}'s Archive</strong></span>
          </div>
          <div className="topbar-right">
            <div className="topbar-pill"><span className="pill-dot"></span>Active Intelligence</div>
            <button className="avatar-btn" onClick={() => setProfileOpen(p => !p)}>{userInitials}</button>
          </div>
        </header>

        {/* Chat area */}
        <div className="chat-area">
          <div className="chat-scroll">

            {/* Welcome prompt */}
            <div className="welcome-bot-msg">
              <p>Welcome to your Firm Intelligence Node. I have indexed your legal archives and am ready to assist with document analysis, cross-referencing, and regulatory compliance queries.</p>
            </div>

            {/* Messages */}
            {messages.map(m =>
              m.role === 'user'
                ? <UserMessage key={m.id} msg={m} />
                : <BotMessage key={m.id} msg={m} onSuggestionClick={send} />
            )}

            {loading && <TypingIndicator />}

            {/* Initial suggestions (welcome state) */}
            {isWelcome && (
              <div className="welcome-suggestions">
                <div className="ws-label">Suggestions</div>
                <div className="ws-chips">
                  {[
                    { label: 'Which SOP is most relevant?', q: 'Which SOP is most relevant to access control?' },
                    { label: 'SOP with most deviations', q: 'Which SOP has the most related deviations?' },
                    { label: 'Needs review?', q: 'Which SOPs need review based on open deviations or audit findings?' },
                    { label: 'Show CAPA status', q: 'Show me the current status of all CAPAs and related decisions' },
                    { label: 'Open deviations', q: 'What are all the open deviations and their impact levels?' },
                    { label: 'Audit findings summary', q: 'Summarize all audit findings and what actions were taken' },
                  ].map((s, i) => (
                    <button key={i} className="ws-chip" onClick={() => send(s.q)}>{s.label}</button>
                  ))}
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input dock */}
          <div className="input-dock">
            <div className="input-area-wrapper">
              <textarea
                ref={inputRef}
                className="chat-input"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Draft your query or request document analysis..."
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                disabled={loading}
                rows={1}
              />
              <div className="input-actions">
                <button className="copy-btn" onClick={handleCopyLast} disabled={messages.filter(m => m.role === 'bot').length === 0}>
                  Copy Transcript
                </button>
                <button className="send-btn" onClick={() => send()} disabled={loading || !input.trim()}>
                  {loading ? <span className="send-spinner"></span> : (
                    <>
                      <span>Transmit</span>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
