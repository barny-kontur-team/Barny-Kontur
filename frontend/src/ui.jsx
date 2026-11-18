import { useEffect, useRef } from 'react';

export function Button({ primary, danger, className = '', type = 'button', ...props }) {
  return <button type={type} className={`button ${primary ? 'primary' : ''} ${danger ? 'danger-button' : ''} ${className}`} {...props} />;
}

export function Badge({ children, tone }) {
  const tones = { 'Не работать': 'red', 'Претензия': 'red', 'Просрочен': 'red', 'Хронический': 'red', 'Без улучшения': 'red', 'Новичок': 'violet', 'Все переданы': 'green', 'Работа завершена': 'green', 'Не наступил': 'green', 'Ожидание срока': 'amber', 'Уменьшается': 'amber' };
  return <span className={`badge ${tone || tones[children] || 'blue'}`}>{children}</span>;
}

export function Metric({ label, value, note }) {
  return <div className="metric"><div className="muted">{label}</div><strong>{value}</strong>{note && <div className="muted">{note}</div>}</div>;
}

export function Field({ label, children, error }) {
  return <label className={`field ${error ? 'invalid' : ''}`}><span>{label}</span>{children}{error && <small role="alert">{error}</small>}</label>;
}

export function Select({ value, onChange, options, empty, ...props }) {
  return <select value={value} onChange={(event) => onChange(event.target.value)} {...props}>
    {empty && <option value="">{empty}</option>}{options.map((option) => <option key={option}>{option}</option>)}
  </select>;
}

export function Table({ headers, children, empty, label }) {
  return <div className="table-wrap"><table aria-label={label}><thead><tr>{headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead>
    <tbody>{empty ? <tr><td className="empty" colSpan={headers.length}>Ничего не найдено.</td></tr> : children}</tbody>
  </table></div>;
}

export function Panel({ title, subtitle, onClose, children, modal = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return <dialog ref={ref} className={modal ? 'modal' : 'drawer'} onCancel={(event) => { event.preventDefault(); onClose(); }}
    onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="panel-inner">
      <header className="panel-header"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button type="button" className="close" aria-label="Закрыть" onClick={onClose}>×</button></header>
      <div className="panel-body">{children}</div>
    </div>
  </dialog>;
}
