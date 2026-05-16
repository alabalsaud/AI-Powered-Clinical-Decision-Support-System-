import { useState, useRef, useEffect } from 'react';
import { auth as authApi } from '../api.js';
import { loginUser } from '../api/cdssApi.js';
import ThemeToggle from '../ThemeToggle.jsx';
import UserAvatar from '../components/UserAvatar.jsx';
import { resizeImageToDataUrl } from '../utils/profileImage.js';

// ─── Helpers ──────────────────────────────────────────────────────────────────
function pwStrength(pw) {
  if (!pw) return { label: '', color: '', pct: 0 };
  let s = 0;
  if (pw.length >= 8)           s++;
  if (pw.length >= 12)          s++;
  if (/[A-Z]/.test(pw))        s++;
  if (/[a-z]/.test(pw))        s++;
  if (/\d/.test(pw))           s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  if (s <= 2) return { label: 'Weak',   color: '#f87171', pct: 22 };
  if (s <= 3) return { label: 'Fair',   color: '#fb923c', pct: 50 };
  if (s <= 4) return { label: 'Good',   color: '#a78bfa', pct: 72 };
  return           { label: 'Strong', color: '#34d399', pct: 100 };
}
function validatePw(pw) {
  if (!pw || pw.length < 12) return 'Minimum 12 characters required.';
  if (!/[A-Z]/.test(pw))     return 'Add at least one uppercase letter.';
  if (!/[a-z]/.test(pw))     return 'Add at least one lowercase letter.';
  if (!/\d/.test(pw))        return 'Add at least one number.';
  return '';
}

// ─── Micro SVG icons ─────────────────────────────────────────────────────────
const Ico = {
  eye:     (off) => off
    ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
    : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  mail:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>,
  lock:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>,
  user:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>,
  badge: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="8" r="6"/><path d="M15.477 12.89L17 22l-5-3-5 3 1.523-9.11"/></svg>,
  shield:<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  check: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>,
  warn:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
  hosp:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 21h18M3 10h18M3 7l9-4 9 4M4 10v11M20 10v11M8 14v3M12 14v3M16 14v3M10 10V7h4v3"/></svg>,
};

// ─── Reusable field ───────────────────────────────────────────────────────────
function Field({ label, icon, type = 'text', value, onChange, placeholder, onKeyDown, right, autoComplete, optional }) {
  return (
    <div className="lp-f">
      <label className="lp-lbl">{label}{optional && <span className="lp-opt"> (optional)</span>}</label>
      <div className="lp-iw">
        {icon && <span className="lp-il">{icon}</span>}
        <input
          className={`lp-in${icon ? ' li' : ''}`}
          type={type} value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          onKeyDown={onKeyDown}
          autoComplete={autoComplete || 'off'}
          spellCheck={false}
        />
        {right && <span className="lp-ir">{right}</span>}
      </div>
    </div>
  );
}

const API = 'http://localhost:8000/api';

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function LoginPage({ onLogin, sessionMessage }) {
  const [tab,      setTab]    = useState('login');
  const [email,    setEmail]  = useState('');
  const [password, setPw]     = useState('');
  const [showPw,   setShowPw] = useState(false);
  const [name,     setName]   = useState('');
  const [username, setUn]     = useState('');
  const [role,     setRole]   = useState('physician');
  const [license,  setLic]    = useState('');
  const [error,    setError]  = useState('');
  const [loading,  setLoad]   = useState(false);
  const [photo,    setPhoto]  = useState(null);
  const photoRef = useRef(null);
  const [ready,    setReady]  = useState(false);
  useEffect(() => { const t = setTimeout(() => setReady(true), 20); return () => clearTimeout(t); }, []);

  // ── Forgot password state ─────────────────────────────────────────────────
  const [fpStep,    setFpStep]   = useState(0); // 0=off 1=email 2=code 3=done
  const [fpEmail,   setFpEmail]  = useState('');
  const [fpCode,    setFpCode]   = useState('');
  const [fpNewPw,   setFpNewPw]  = useState('');
  const [fpShowPw,  setFpShowPw] = useState(false);
  const [fpError,   setFpError]  = useState('');
  const [fpSuccess, setFpSuccess]= useState('');

  function openForgot() {
    setFpStep(1); setFpEmail(email); setFpCode(''); setFpNewPw('');
    setFpError(''); setFpSuccess('');
  }
  function closeForgot() { setFpStep(0); setFpError(''); setFpSuccess(''); }

  async function fpSendCode() {
    if (!fpEmail.trim()) { setFpError('Enter your registered email.'); return; }
    setLoad(true); setFpError(''); setFpSuccess('');
    try {
      const r = await fetch(`${API}/auth/forgot-password`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: fpEmail.trim() }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Failed to send code.');
      setFpSuccess('Code sent! Check your inbox (and spam folder).');
      setFpStep(2);
    } catch(e) { setFpError(e.message); }
    finally { setLoad(false); }
  }

  async function fpResetPassword() {
    if (!fpCode.trim()) { setFpError('Enter the 6-digit code from your email.'); return; }
    if (fpNewPw.length < 8) { setFpError('New password must be at least 8 characters.'); return; }
    setLoad(true); setFpError(''); setFpSuccess('');
    try {
      const r = await fetch(`${API}/auth/reset-password`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: fpEmail.trim(), code: fpCode.trim(), new_password: fpNewPw }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || 'Reset failed.');
      setFpStep(3); setFpSuccess(d.message || 'Password reset successfully!');
    } catch(e) { setFpError(e.message); }
    finally { setLoad(false); }
  }

  const strength = pwStrength(password);

  function switchTab(t) {
    setTab(t); setError('');
    setEmail(''); setPw(''); setShowPw(false);
    setName(''); setUn(''); setLic(''); setRole('physician');
    setPhoto(null);
    if (photoRef.current) photoRef.current.value = '';
  }

  async function doLogin() {
    if (!email.trim() || !password) { setError('Enter your email and password.'); return; }
    setLoad(true); setError('');
    try { const d = await loginUser(email.trim(), password); onLogin(d.user); }
    catch (e) { setError(e.message || 'Invalid credentials. Please try again.'); }
    finally { setLoad(false); }
  }

  async function doRegister() {
    const em = email.trim(), un = username.trim(), nm = name.trim();
    if (!nm || !em || !password || !un) { setError('All starred fields are required.'); return; }
    const e2 = validatePw(password);
    if (e2) { setError(e2); return; }
    setLoad(true); setError('');
    try {
      await authApi.register({ username: un, email: em, full_name: nm, password, role,
        license_number: license.trim() || null, profile_image: photo || null });
      const d = await authApi.login(em, password);
      onLogin(d.user);
    } catch (e) { setError(e.message || 'Registration failed.'); }
    finally { setLoad(false); }
  }

  const EyeBtn = () => (
    <button type="button" className="lp-eye" onClick={() => setShowPw(v => !v)} aria-label="Toggle password">
      {Ico.eye(showPw)}
    </button>
  );

  return (
    <div className={`lp-root${ready ? ' lp-rdy' : ''}`}>

      {/* Decorative layer */}
      <div className="lp-mesh"  aria-hidden />
      <div className="lp-orb a" aria-hidden />
      <div className="lp-orb b" aria-hidden />
      <div className="lp-orb c" aria-hidden />

      {/* Top bar */}
      <header className="lp-bar">
        <div className="lp-brand">
          <div className="lp-brand-icon">{Ico.hosp}</div>
          <span className="lp-brand-name">AI · CDSS</span>
          <span className="lp-brand-pill">Beta</span>
        </div>
        <ThemeToggle />
      </header>

      {/* Body */}
      <div className="lp-body">

        {/* ── LEFT ─────────────────────────────────────────── */}
        <aside className="lp-hero">
          <div className="lp-hero-inner">

            <div className="lp-hero-tag">
              <span className="lp-tag-dot" />
              Powered by Llama 3 · Ollama
            </div>

            <h1 className="lp-hero-h" style={{ textAlign: 'center', fontFamily: '"Times New Roman", Times, serif' }}>
              Clinical AI at<br />Your Fingertips
            </h1>
            <p className="lp-hero-p" style={{ textAlign: 'center', fontFamily: '"Times New Roman", Times, serif' }}>
            <span style={{ whiteSpace: 'nowrap' }}>       Intelligent decision support that helps physicians </span>
              diagnose faster, prescribe safer, and document smarter.
            </p>

            {/* Stats */}
            <div className="lp-stats">
              {[['5+','AI Modules']].map(([n,l])=>(
                <div key={l} className="lp-stat">
                  <div className="lp-stat-n">{n}</div>
                  <div className="lp-stat-l">{l}</div>
                </div>
              ))}
            </div>

            {/* Features — 2×2 horizontal grid */}
            <div className="lp-feats">
              {[
                { ic:'🧠', tx:'LLM-powered differential diagnosis',  sub:'Multi-agent AI pipeline' },
                { ic:'💊', tx:'Real-time drug interaction checks',    sub:'DrugBank integration'    },
                { ic:'📋', tx:'AI-generated treatment plans',         sub:'Evidence-based protocols'},
                { ic:'🔒', tx:'HIPAA-compliant & encrypted',          sub:'Secure clinical data'    },
              ].map(({ ic, tx, sub }) => (
                <div key={tx} className="lp-feat">
                  <span className="lp-feat-ic">{ic}</span>
                  <div className="lp-feat-body">
                    <span className="lp-feat-tx">{tx}</span>
                    <span className="lp-feat-sub">{sub}</span>
                  </div>
                </div>
              ))}
            </div>

           
          </div>
        </aside>

        {/* ── RIGHT ────────────────────────────────────────── */}
        <section className="lp-right">
          <div className="lp-card">

            {/* Session warn */}
            {sessionMessage && (
              <div className="lp-session">⏱ {sessionMessage}</div>
            )}

            {/* Header — CENTERED */}
            <div className="lp-card-hd">
              <div className="lp-card-logo">{Ico.hosp}</div>
              <h2 className="lp-card-title">
                {tab === 'login' ? 'Welcome back' : 'Create account'}
              </h2>
              <p className="lp-card-sub">
                {tab === 'login'
                  ? 'Sign in to your clinical workspace'
                  : 'Join as a healthcare professional'}
              </p>
            </div>

            {/* Tabs */}
            <div className="lp-tabs" role="tablist">
              {[['login','Sign In'],['register','Register']].map(([k,l])=>(
                <button key={k} role="tab" type="button"
                  className={`lp-tab${tab===k?' on':''}`}
                  onClick={()=>switchTab(k)}>{l}</button>
              ))}
            </div>

            {/* Error */}
            {error && (
              <div className="lp-err" role="alert">
                <span style={{flexShrink:0,display:'flex'}}>{Ico.warn}</span>
                {error}
              </div>
            )}

            {/* ── Form scroll body ──────────────────────── */}
            <div className="lp-scroll">

              {/* SIGN IN */}
              {tab === 'login' && (
                <div className="lp-form">
                  <Field label="Email Address" icon={Ico.mail} type="email"
                    value={email} onChange={setEmail} placeholder="doctor@hospital.sa"
                    autoComplete="email"
                  />
                  <Field label="Password" icon={Ico.lock}
                    type={showPw ? 'text' : 'password'}
                    value={password} onChange={setPw}
                    placeholder="••••••••••••"
                    onKeyDown={e => e.key==='Enter' && doLogin()}
                    autoComplete="current-password"
                    right={<EyeBtn />}
                  />
                  <button className="lp-btn" onClick={doLogin} disabled={loading}>
                    {loading
                      ? <><span className="lp-spin"/>Authenticating…</>
                      : <>{Ico.shield}<span>Sign In Securely</span></>}
                  </button>
                  <div style={{ textAlign: 'center', marginTop: 10 }}>
                    <button type="button" className="lp-forgot-link" onClick={openForgot}>
                      Forgot password?
                    </button>
                  </div>
                </div>
              )}

              {/* REGISTER */}
              {tab === 'register' && (
                <div className="lp-form">
                  <div className="lp-r2">
                    <Field label="Full Name *" icon={Ico.user} value={name} onChange={setName} placeholder="Dr. Full Name"/>
                    <Field label="Username *"  icon={Ico.user} value={username} onChange={setUn} placeholder="dr.name"/>
                  </div>
                  <Field label="Email *" icon={Ico.mail} type="email"
                    value={email} onChange={setEmail} placeholder="doctor@hospital.sa" autoComplete="email"/>

                  <div className="lp-r2">
                    <Field label="License No." icon={Ico.badge} value={license} onChange={setLic} placeholder="SAU-XXXXX"/>
                    <div className="lp-f">
                      <label className="lp-lbl">Role</label>
                      <div className="lp-iw">
                        <select className="lp-in lp-sel" value={role} onChange={e=>setRole(e.target.value)}>
                          {['physician','nurse','pharmacist'].map(r=>(
                            <option key={r} value={r}>{r[0].toUpperCase()+r.slice(1)}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>

                  {/* Password */}
                  <div className="lp-f">
                    <label className="lp-lbl">Password *</label>
                    <div className="lp-iw">
                      <span className="lp-il">{Ico.lock}</span>
                      <input className="lp-in li"
                        type={showPw ? 'text' : 'password'}
                        value={password} onChange={e=>setPw(e.target.value)}
                        placeholder="Min. 12 chars · A–Z · a–z · 0–9"
                        autoComplete="new-password"
                      />
                      <span className="lp-ir"><EyeBtn /></span>
                    </div>
                    {password && (
                      <div className="lp-str">
                        <div className="lp-str-track">
                          <div className="lp-str-fill" style={{width:`${strength.pct}%`,background:strength.color}}/>
                        </div>
                        <span className="lp-str-lbl" style={{color:strength.color}}>{strength.label}</span>
                      </div>
                    )}
                  </div>

                  {/* Profile photo (compact) */}
                  <div className="lp-f">
                    <label className="lp-lbl">Photo <span className="lp-opt">(optional)</span></label>
                    <div className="lp-photo-row">
                      <UserAvatar user={photo?{profile_image:photo,full_name:name}:{full_name:name||'DR'}} size={40}/>
                      <div className="lp-photo-actions">
                        <input ref={photoRef} type="file" accept="image/jpeg,image/png,image/webp"
                          className="lp-file"
                          onChange={async e=>{
                            const f=e.target.files?.[0];
                            if(!f){setPhoto(null);return;}
                            try{setPhoto(await resizeImageToDataUrl(f,320,0.82));}
                            catch(err){setError(err.message||'Image error');}
                          }}
                        />
                        {photo&&<button type="button" className="lp-rm"
                          onClick={()=>{setPhoto(null);if(photoRef.current)photoRef.current.value='';}}>× Remove</button>}
                      </div>
                    </div>
                  </div>

                  <button className="lp-btn" onClick={doRegister} disabled={loading}>
                    {loading
                      ? <><span className="lp-spin"/>Creating Account…</>
                      : <>{Ico.check}<span>Create My Account</span></>}
                  </button>
                  <div className="lp-demo">
                    <span className="lp-dot-live"/>
                    Use a new email not already registered in the system.
                  </div>
                </div>
              )}
            </div>
            {/* ── End scroll body ─────────────────────── */}

           

          </div>
        </section>
      </div>

      {/* ── Forgot Password Modal ──────────────────────────────────────── */}
      {fpStep > 0 && (
        <div className="lp-modal-overlay" onClick={closeForgot}>
          <div className="lp-modal" onClick={e => e.stopPropagation()}>

            {/* Step 1 — Enter email */}
            {fpStep === 1 && (<>
              <div className="lp-modal-hd">
                <div className="lp-modal-ico">🔑</div>
                <h3 className="lp-modal-title">Reset Password</h3>
                <p className="lp-modal-sub">Enter your registered email and we'll send a 6-digit code.</p>
              </div>
              {fpError && <div className="lp-err" role="alert"><span style={{flexShrink:0,display:'flex'}}>{Ico.warn}</span>{fpError}</div>}
              <Field label="Registered Email" icon={Ico.mail} type="email"
                value={fpEmail} onChange={setFpEmail} placeholder="doctor@hospital.sa"
                onKeyDown={e => e.key==='Enter' && fpSendCode()}
              />
              <button className="lp-btn" onClick={fpSendCode} disabled={loading} style={{marginTop:8}}>
                {loading ? <><span className="lp-spin"/>Sending…</> : <>📧 Send Reset Code</>}
              </button>
              <button type="button" className="lp-forgot-link" onClick={closeForgot} style={{display:'block',margin:'12px auto 0'}}>Cancel</button>
            </>)}

            {/* Step 2 — Enter code + new password */}
            {fpStep === 2 && (<>
              <div className="lp-modal-hd">
                <div className="lp-modal-ico">📨</div>
                <h3 className="lp-modal-title">Enter Reset Code</h3>
                <p className="lp-modal-sub">Check your inbox at <strong style={{color:'#a78bfa'}}>{fpEmail}</strong>. Code expires in 10 minutes.</p>
              </div>
              {fpSuccess && <div className="lp-success" role="status">✅ {fpSuccess}</div>}
              {fpError   && <div className="lp-err" role="alert"><span style={{flexShrink:0,display:'flex'}}>{Ico.warn}</span>{fpError}</div>}
              <Field label="6-Digit Code" icon={Ico.check} value={fpCode}
                onChange={v => setFpCode(v.replace(/\D/g,'').slice(0,6))}
                placeholder="••••••"
                onKeyDown={e => e.key==='Enter' && fpResetPassword()}
              />
              <div className="lp-f">
                <label className="lp-lbl">New Password</label>
                <div className="lp-iw">
                  <span className="lp-il">{Ico.lock}</span>
                  <input className="lp-in li"
                    type={fpShowPw ? 'text' : 'password'}
                    value={fpNewPw} onChange={e => setFpNewPw(e.target.value)}
                    placeholder="Min. 8 characters"
                    onKeyDown={e => e.key==='Enter' && fpResetPassword()}
                  />
                  <span className="lp-ir">
                    <button type="button" className="lp-eye" onClick={() => setFpShowPw(v=>!v)}>{Ico.eye(fpShowPw)}</button>
                  </span>
                </div>
              </div>
              <button className="lp-btn" onClick={fpResetPassword} disabled={loading} style={{marginTop:8}}>
                {loading ? <><span className="lp-spin"/>Resetting…</> : <>🔒 Reset Password</>}
              </button>
              <button type="button" className="lp-forgot-link" onClick={() => setFpStep(1)} style={{display:'block',margin:'10px auto 0'}}>← Back</button>
            </>)}

            {/* Step 3 — Success */}
            {fpStep === 3 && (<>
              <div className="lp-modal-hd">
                <div className="lp-modal-ico" style={{fontSize:48}}>✅</div>
                <h3 className="lp-modal-title">Password Reset!</h3>
                <p className="lp-modal-sub">{fpSuccess}</p>
              </div>
              <button className="lp-btn" onClick={closeForgot} style={{marginTop:8}}>
                Sign In Now
              </button>
            </>)}

          </div>
        </div>
      )}
    </div>
  );
}
