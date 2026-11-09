import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { Dialog } from './UI';
import { calendarDays, dayDate, historyDay, moveDay } from './historyDates';
import type { HistoryRange } from './historyDates';

const rangeLabel = (range: HistoryRange) => range.start
  ? range.end && range.end !== range.start ? `${range.start} ~ ${range.end}` : range.start
  : '전체 기간';

export default function HistoryDateRange({ value, counts, onChange }: {
  value: HistoryRange; counts: Map<string, number>; onChange: (range: HistoryRange) => void;
}) {
  const [open, setOpen] = useState(false);
  return <><button className="button secondary history-date-trigger" aria-haspopup="dialog" onClick={() => setOpen(true)}>
    <CalendarDays aria-hidden="true" size={17} /><span>{rangeLabel(value)}</span><span className="sr-only"> · 수거 기간 선택</span>
  </button>{open && <RangeCalendar value={value} counts={counts} onClose={() => setOpen(false)} onApply={range => { onChange(range); setOpen(false); }} />}</>;
}

function RangeCalendar({ value, counts, onClose, onApply }: {
  value: HistoryRange; counts: Map<string, number>; onClose: () => void; onApply: (range: HistoryRange) => void;
}) {
  const today = historyDay(new Date().toISOString());
  const [draft, setDraft] = useState(value);
  const [active, setActive] = useState<'start' | 'end'>('start');
  const [focusDay, setFocusDay] = useState(value.start || today);
  const [month, setMonth] = useState((value.start || today).slice(0, 7));
  const grid = useRef<HTMLDivElement>(null);
  const needsFocus = useRef(false);
  const year = Number(month.slice(0, 4)), monthNumber = Number(month.slice(5));
  const recordedYears = [...counts.keys()].map(day => Number(day.slice(0, 4)));
  const minYear = Math.min(Number(today.slice(0, 4)) - 10, ...recordedYears, year);
  const maxYear = Math.max(Number(today.slice(0, 4)) + 10, ...recordedYears, year);
  useEffect(() => {
    if (needsFocus.current) {
      grid.current?.querySelector<HTMLButtonElement>(`[data-day="${focusDay}"]`)?.focus();
      needsFocus.current = false;
    }
  }, [focusDay, month]);

  function shiftMonth(amount: number) {
    const date = dayDate(month + '-01');
    date.setUTCMonth(date.getUTCMonth() + amount);
    const next = date.toISOString().slice(0, 7);
    setMonth(next); setFocusDay(next + '-01');
  }
  function pick(day: string) {
    setMonth(day.slice(0, 7)); setFocusDay(day);
    if (active === 'start') {
      setDraft({ start: day, end: draft.end >= day ? draft.end : '' }); setActive('end');
    } else {
      setDraft({ start: draft.start && draft.start < day ? draft.start : day, end: draft.start > day ? draft.start : day });
    }
  }
  function keys(event: KeyboardEvent<HTMLButtonElement>, day: string) {
    const deltas: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 };
    let next = day;
    if (event.key in deltas) next = moveDay(day, deltas[event.key]);
    else if (event.key === 'Home') next = moveDay(day, -dayDate(day).getUTCDay());
    else if (event.key === 'End') next = moveDay(day, 6 - dayDate(day).getUTCDay());
    else if (event.key === 'PageUp' || event.key === 'PageDown') {
      const date = dayDate(day); date.setUTCDate(1); date.setUTCMonth(date.getUTCMonth() + (event.key === 'PageUp' ? -1 : 1)); next = date.toISOString().slice(0, 10);
    } else return;
    event.preventDefault(); needsFocus.current = true; setFocusDay(next); setMonth(next.slice(0, 7));
  }
  const effectiveEnd = draft.end || draft.start;
  const days = calendarDays(month);
  return <Dialog title="수거 기록 기간 선택" subtitle="초록색 날짜에는 수거 기록이 있습니다. 시작일과 종료일을 선택하세요." onClose={onClose}>
    <div className="history-calendar">
      <div className="calendar-range-fields" role="group" aria-label="선택할 날짜">
        {(['start', 'end'] as const).map(field => <button key={field} className={active === field ? 'active' : ''} aria-pressed={active === field} onClick={() => { setActive(field); const day = draft[field] || draft.start || today; setMonth(day.slice(0, 7)); setFocusDay(day); }}>
          <span>{field === 'start' ? '시작일' : '종료일'}</span><strong>{draft[field] || '날짜 선택'}</strong>
        </button>)}
      </div>
      <div className="calendar-month-nav"><button className="icon-button" aria-label="이전 달" onClick={() => shiftMonth(-1)}><ChevronLeft aria-hidden="true" size={20} /></button>
        <div><select aria-label="연도" value={year} onChange={e => { const next = `${e.target.value}-${month.slice(5)}`; setMonth(next); setFocusDay(next + '-01'); }}>{Array.from({ length: maxYear - minYear + 1 }, (_, i) => minYear + i).map(y => <option key={y} value={y}>{y}년</option>)}</select>
          <select aria-label="월" value={monthNumber} onChange={e => { const next = `${year}-${e.target.value.padStart(2, '0')}`; setMonth(next); setFocusDay(next + '-01'); }}>{Array.from({ length: 12 }, (_, i) => i + 1).map(m => <option key={m} value={m}>{m}월</option>)}</select></div>
        <button className="icon-button" aria-label="다음 달" onClick={() => shiftMonth(1)}><ChevronRight aria-hidden="true" size={20} /></button></div>
      <div ref={grid} role="grid" aria-label={`${year}년 ${monthNumber}월 수거 기록 달력`} className="calendar-grid">
        <div role="row" className="calendar-weekdays">{['일', '월', '화', '수', '목', '금', '토'].map(day => <span key={day} role="columnheader">{day}</span>)}</div>
        {Array.from({ length: days.length / 7 }, (_, week) => <div role="row" className="calendar-week" key={week}>{days.slice(week * 7, week * 7 + 7).map(day => {
          const count = counts.get(day) ?? 0, selected = day === draft.start || day === effectiveEnd;
          const inRange = !!draft.start && day >= draft.start && day <= effectiveEnd;
          const label = `${day.replace(/-/g, '.')} · ${count ? `수거 기록 ${count}건` : '수거 기록 없음'}`;
          return <div role="gridcell" aria-selected={inRange} key={day}><button data-day={day} tabIndex={focusDay === day ? 0 : -1} aria-label={label} aria-current={day === today ? 'date' : undefined} title={label}
            className={`calendar-day ${day.startsWith(month) ? '' : 'other-month'} ${count ? 'has-records' : ''} ${inRange ? 'in-range' : ''} ${selected ? 'range-endpoint' : ''}`}
            onFocus={() => setFocusDay(day)} onKeyDown={e => keys(e, day)} onClick={() => pick(day)}><span>{Number(day.slice(8))}</span><i aria-hidden="true" /></button></div>;
        })}</div>)}
      </div>
      <div className="calendar-legend"><span><i />수거 기록 있음</span><small>양쪽 날짜를 포함해 조회합니다.</small></div>
      <div className="calendar-shortcuts"><button className="button subtle small" onClick={() => { setDraft({ start: today, end: today }); setMonth(today.slice(0, 7)); setFocusDay(today); }}>오늘</button><button className="button subtle small" onClick={() => { setDraft({ start: moveDay(today, -6), end: today }); setMonth(today.slice(0, 7)); setFocusDay(today); }}>최근 7일</button><button className="button subtle small" onClick={() => setDraft({ start: '', end: '' })}>전체 기간</button></div>
      <div className="calendar-selection" role="status">{draft.start ? `${rangeLabel({ start: draft.start, end: effectiveEnd })} · ${[...counts].filter(([day]) => day >= draft.start && day <= effectiveEnd).reduce((sum, [, count]) => sum + count, 0)}건` : '전체 기간의 수거 기록을 표시합니다.'}</div>
      <div className="modal-actions"><button className="button secondary" onClick={onClose}>취소</button><button className="button primary" onClick={() => onApply({ start: draft.start, end: effectiveEnd })}>기간 적용</button></div>
    </div>
  </Dialog>;
}
