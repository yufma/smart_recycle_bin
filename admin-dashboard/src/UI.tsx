import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { CSSProperties, ReactNode } from 'react';
import { Leaf, X, ArrowUpRight, Inbox } from 'lucide-react';
import { compartmentName, compartments, dateTime, fillStatus, statusColor, statusText } from './types';
import type { Bin, Building, Fills, Status } from './types';
import { floorLabel, floorsOf } from './floors';

export function Logo({ light = false, onHome }: { light?: boolean; onHome?: () => void }) {
  return <a className={`brand ${light ? 'light' : ''}`} href="#dashboard" aria-label="inloop 홈으로 이동" onClick={onHome ? e => { e.preventDefault(); onHome(); } : undefined}><span className="brand-symbol"><Leaf aria-hidden="true" size={25} strokeWidth={1.7} /></span><span>inloop<span className="brand-dot">.</span></span></a>;
}
export function Badge({ status }: { status: Status }) { return <span className={`status-badge ${status}`}><i />{statusText[status]}</span>; }
export function BinArt({ fill, status = 'normal', large = false }: { fill: number | null; status?: Status; large?: boolean }) {
  return <div className={`bin-art ${status} ${large ? 'large' : ''}`} aria-hidden="true"><div className="bin-handle" /><div className="bin-lid" /><div className="bin-body"><div className="bin-fill" style={{ height: `${fill ?? 0}%` }} /><div className="bin-mark"><Leaf aria-hidden="true" size={large ? 25 : 16} strokeWidth={1.5} /></div><div className="bin-groove left" /><div className="bin-groove right" /></div><i className="bin-wheel left" /><i className="bin-wheel right" /></div>;
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
export function FloorTabs({ value, floors, basementFloors = 0, onChange, all = false }: { value: number; floors: number; basementFloors?: number; onChange: (n: number) => void; all?: boolean }) {
  return <div className="floor-tabs" role="group" aria-label="층 선택">{all && <button aria-pressed={value === 0} className={value === 0 ? 'active' : ''} onClick={() => onChange(0)}>전체 층</button>}{floorsOf({ floors, basement_floors: basementFloors }).map(f => <button key={f} aria-label={floorLabel(f)} aria-pressed={value === f} className={value === f ? 'active' : ''} onClick={() => onChange(f)}>{floorLabel(f, true)}</button>)}</div>;
}
export function Toggle({ checked, onChange, label, disabled = false }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return <label className="toggle-label"><input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} disabled={disabled} /><span className="toggle-track"><span /></span><span>{label}</span></label>;
}
export function Empty({ title, children, icon, action }: { title: string; children?: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon" aria-hidden="true">{icon || <Inbox aria-hidden="true" size={25} />}</div><h3>{title}</h3>{children && <p>{children}</p>}{action && <div className="empty-action">{action}</div>}</div>;
}
export function Dialog({ title, subtitle, children, onClose, wide = false }: { title: string; subtitle?: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const titleId = useId(), descriptionId = useId();
  const close = useRef(onClose); close.current = onClose;
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    const overflow = document.body.style.overflow;
    const appRoot = document.getElementById('root');
    const wasInert = appRoot?.inert ?? false;
    if (appRoot) appRoot.inert = true;
    document.body.style.overflow = 'hidden';
    box.current?.focus();
    function keys(e: KeyboardEvent) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close.current(); }
      if (e.key === 'Tab') {
        const items = Array.from(box.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]') ?? []).filter(el => el.getClientRects().length > 0);
        if (!items.length) { e.preventDefault(); return; }
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === box.current)) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && (document.activeElement === last || document.activeElement === box.current)) { e.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener('keydown', keys);
    return () => { document.body.style.overflow = overflow; if (appRoot) appRoot.inert = wasInert; document.removeEventListener('keydown', keys); if (before?.isConnected) before.focus({ preventScroll: true }); };
  }, []);
  return createPortal(<div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}><div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={subtitle ? descriptionId : undefined} tabIndex={-1} ref={box}>
    <div className="modal-header"><div><h2 id={titleId}>{title}</h2>{subtitle && <p id={descriptionId}>{subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label="닫기"><X size={20} aria-hidden="true" /></button></div>{children}</div></div>, document.body);
}
export function SectionTitle({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="section-title"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2>{description && <p>{description}</p>}</div>{action}</div>;
}
export function MiniLink({ children, onClick }: { children: ReactNode; onClick: () => void }) { return <button className="text-link" onClick={onClick}>{children}<ArrowUpRight aria-hidden="true" size={15} /></button>; }
export function ColorDot({ color }: { color: string }) { return <i className="color-dot" style={{ '--dot': color } as CSSProperties} />; }
