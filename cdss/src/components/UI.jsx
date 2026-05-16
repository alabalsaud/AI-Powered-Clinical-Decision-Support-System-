// ─── SHARED UI HELPERS ────────────────────────────────────────────────────────

export function confClass(c) {
  return c >= 75 ? 'conf-high' : c >= 50 ? 'conf-med' : 'conf-low';
}

export function ConfBar({ value }) {
  return (
    <div className={`conf-wrap ${confClass(value)}`} style={{ flex: 1 }}>
      <div className="conf-bar">
        <div className="conf-fill" style={{ width: `${value}%` }} />
      </div>
      <span className="text-mono text-xs" style={{ fontWeight: 700, minWidth: 32 }}>{value}%</span>
    </div>
  );
}

export function SafetyBadge({ status }) {
  if (status === 'Critical' || status === 'Contraindicated')
    return <span className="badge badge-red">⛔ {status}</span>;
  if (status === 'Major')
    return <span className="badge badge-red">🔴 {status}</span>;
  if (status === 'Moderate' || status === 'Warning')
    return <span className="badge badge-amber">⚠️ {status}</span>;
  return <span className="badge badge-green">✅ Safe</span>;
}

export function StatusBadge({ status }) {
  const map = {
    Completed: 'badge-green',
    Active:     'badge-green',
    Confirmed:  'badge-green',
    Blocked:    'badge-red',
    Pending:    'badge-amber',
    'Under Review': 'badge-amber',
    Warning:    'badge-amber',
    Safe:       'badge-green',
  };
  return <span className={`badge ${map[status] || 'badge-blue'}`}>{status}</span>;
}

export function LoadingOverlay({ message }) {
  return (
    <div className="loading-overlay">
      <div className="loading-ring" />
      <div className="loading-text">{message}</div>
    </div>
  );
}

export function EmptyState({ icon, title, sub }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <div className="empty-title">{title}</div>
      {sub && <div className="empty-sub">{sub}</div>}
    </div>
  );
}

export function Modal({ title, onClose, size = '', children, footer }) {
  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${size}`}>
        <div className="modal-header">
          <div className="modal-title">{title}</div>
          <div className="modal-close" onClick={onClose}>✕</div>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  );
}

export function Toggle({ value, onChange }) {
  return (
    <div
      className="toggle-wrap"
      style={{ background: value ? 'var(--accent)' : 'var(--surface3)' }}
      onClick={() => onChange(!value)}
    >
      <div className="toggle-knob" style={{ left: value ? 21 : 3 }} />
    </div>
  );
}

export function Steps({ steps, current }) {
  return (
    <div className="steps">
      {steps.map((s, i) => (
        <div key={i} className={`step ${i < current ? 'done' : ''} ${i === current ? 'active' : ''}`}>
          <div className="step-dot">{i < current ? '✓' : i + 1}</div>
          <div className="step-lbl">{s}</div>
        </div>
      ))}
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs">
      {tabs.map(t => (
        <div key={t} className={`tab ${active === t ? 'active' : ''}`} onClick={() => onChange(t)}>
          {t}
        </div>
      ))}
    </div>
  );
}
