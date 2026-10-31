import { useEffect, useRef } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { Leaf, X, ArrowUpRight, Inbox } from 'lucide-react';
import { compartmentName, compartments, dateTime, fillStatus, statusColor, statusText } from './types';
import type { Bin, Building, Fills, Status } from './types';

export function Logo({ light = false }: { light?: boolean }) {
  return <div className={`brand ${light ? 'light' : ''}`}><span className="brand-symbol"><Leaf size={25} strokeWidth={1.7} /></span><span>reloop<span className="brand-dot">.</span></span></div>;
}
export function Badge({ status }: { status: Status }) { return <span className={`status-badge ${status}`}><i />{statusText[status]}</span>; }
export function BinArt({ fill, status = 'normal', large = false }: { fill: number | null; status?: Status; large?: boolean }) {
  return <div className={`bin-art ${status} ${large ? 'large' : ''}`} aria-hidden="true"><div className="bin-handle" /><div className="bin-lid" /><div className="bin-body"><div className="bin-fill" style={{ height: `${fill ?? 0}%` }} /><div className="bin-mark"><Leaf size={large ? 25 : 16} strokeWidth={1.5} /></div><div className="bin-groove left" /><div className="bin-groove right" /></div><i className="bin-wheel left" /><i className="bin-wheel right" /></div>;
}
export function CompartmentRow({ values, building, large = false }: { values: Fills; building: Building; large?: boolean }) {
  return <div className={`compartment-row ${large ? 'large' : ''}`} role="group" aria-label="칸별 적재율">{compartments.map(c => {
    const value = values[c];
    return <div key={c}><span>{compartmentName[c]}</span><b className={value === null ? 'waiting-value' : ''}>{value === null ? '수신 대기' : `${Math.round(value)}%`}</b><i><em style={{ width: `${value ?? 0}%`, background: statusColor[fillStatus(value, building)] }} /></i></div>;
  })}</div>;
}
export function SensorNotice({ bin, details = false }: { bin: Bin; details?: boolean }) {
  if (bin.reading_source !== 'actual' || (!bin.partial_reading && !bin.stale_compartments?.length)) return null;
  return <div className="sensor-notice" role="note"><span>{bin.partial_reading ? '일부 칸 수신 대기 · 최신 값만 반영' : '최신 칸 값 수신 대기'}</span>{details && !!bin.stale_compartments?.length && <p>이전 기록(계산에서 제외): {bin.stale_compartments.map(c => `${compartmentName[c]} ${bin.last_compartments?.[c] ?? '—'}% · ${dateTime(bin.compartment_measured_at?.[c] ?? null)}`).join(' / ')}</p>}</div>;
}
export function FloorTabs({ value, floors, onChange, all = false }: { value: number; floors: number; onChange: (n: number) => void; all?: boolean }) {
  return <div className="floor-tabs" role="group" aria-label="층 선택">{all && <button className={value === 0 ? 'active' : ''} onClick={() => onChange(0)}>전체 층</button>}{Array.from({ length: floors }, (_, i) => i + 1).map(f => <button key={f} className={value === f ? 'active' : ''} onClick={() => onChange(f)}>{f}F</button>)}</div>;
}
export function Toggle({ checked, onChange, label, disabled = false }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return <label className="toggle-label"><input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} disabled={disabled} /><span className="toggle-track"><span /></span><span>{label}</span></label>;
}
export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon">{icon || <Inbox size={25} />}</div><strong>{title}</strong>{children && <p>{children}</p>}</div>;
}
export function Dialog({ title, subtitle, children, onClose, wide = false }: { title: string; subtitle?: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const close = useRef(onClose); close.current = onClose;
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    box.current?.focus();
    function keys(e: KeyboardEvent) {
      if (e.key === 'Escape') close.current();
      if (e.key === 'Tab') {
        const items = box.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]');
        if (!items?.length) return;
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === box.current)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && (document.activeElement === last || document.activeElement === box.current)) { e.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener('keydown', keys);
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', keys); before?.focus(); };
  }, []);
  return <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}><div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={box}>
    <div className="modal-header"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label="닫기"><X size={20} /></button></div>{children}</div></div>;
}
export function SectionTitle({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="section-title"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>;
}
export function MiniLink({ children, onClick }: { children: ReactNode; onClick: () => void }) { return <button className="text-link" onClick={onClick}>{children}<ArrowUpRight size={15} /></button>; }
export function ColorDot({ color }: { color: string }) { return <i className="color-dot" style={{ '--dot': color } as CSSProperties} />; }
