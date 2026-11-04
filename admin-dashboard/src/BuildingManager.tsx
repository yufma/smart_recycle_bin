import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Building2, Check, Loader2, Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react';
import type { BuildingSummary, WorkspaceResponse } from './types';
import { Dialog, Empty } from './UI';

export type BuildingAction = (path: string, data?: unknown, method?: string, message?: string) => Promise<boolean>;
const templates = [
  { id: 'empty', title: '빈 건물', detail: '도면과 쓰레기통 위치를 직접 등록' },
  { id: 'basic', title: '미래관 기본 시연', detail: '3층 · 쓰레기통 12개 · 기본 더미 데이터' },
  { id: 'inha', title: '인하대학교 캠퍼스', detail: '실제 공개 지도 · 쓰레기통은 직접 배치' },
  { id: 'large', title: '큰 건물 예시', detail: '5층 · 쓰레기통 30개' },
  { id: 'library', title: '가상 도서관 예시', detail: '6층 · 정석학술정보관의 실제 도면과 별개' },
  { id: 'civic', title: '복합청사 예시', detail: '8층 · 두 동을 잇는 연결동' },
  { id: 'round', title: '곡선형 건물 예시', detail: '4층 · 트랙 모양 복도' },
];

export default function BuildingManager({ s, busy, error, action, onClose, onSelected }: {
  s: WorkspaceResponse; busy: boolean; error: string; action: BuildingAction; onClose: () => void; onSelected: () => void;
}) {
  const [view, setView] = useState<'list' | 'add' | 'rename' | 'delete'>('list');
  const [target, setTarget] = useState<BuildingSummary | null>(null);
  const [name, setName] = useState('');
  const [template, setTemplate] = useState('empty');
  const [floors, setFloors] = useState(1);
  const nameInput = useRef<HTMLInputElement>(null);
  useEffect(() => { if (view === 'add' || view === 'rename') nameInput.current?.focus(); }, [view]);
  function edit(item: BuildingSummary, next: 'rename' | 'delete') { setTarget(item); setName(item.name); setView(next); }
  const pending = <Loader2 aria-hidden="true" size={16} className="spin" />;
  return <Dialog title={view === 'add' ? '건물 추가' : view === 'rename' ? '건물 이름 바꾸기' : view === 'delete' ? '건물을 삭제할까요?' : '건물 관리'}
    subtitle={view === 'list' ? `관리 중인 건물 ${s.buildings.length}개 · 건물별로 배치와 수거 기록을 저장합니다.` : undefined} onClose={onClose}>
    {view !== 'list' && <button className="text-link building-back" disabled={busy} onClick={() => setView('list')}><ArrowLeft aria-hidden="true" size={15} />건물 목록</button>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {view === 'list' ? <>
      <div className="building-manager-list">{s.buildings.map(item => <div className={`building-manager-row ${item.id === s.workspace_id ? 'current' : ''}`} key={item.id}>
        <button className="building-choice" disabled={busy} aria-current={item.id === s.workspace_id ? 'true' : undefined}
          onClick={async () => { if (item.id === s.workspace_id) { onClose(); return; } if (await action(`/buildings/${item.id}/select`, {}, 'POST', `${item.name}으로 전환했습니다.`)) onSelected(); }}>
          <span className="building-choice-icon"><Building2 aria-hidden="true" size={21} /></span><span><strong>{item.name}</strong><small>{item.floors}개 층 · 쓰레기통 {item.bin_count}개</small></span>
          {item.id === s.workspace_id ? <span className="building-current"><Check aria-hidden="true" size={13} />현재</span> : <ArrowRight aria-hidden="true" size={16} />}
        </button>
        <div className="building-row-actions"><button className="icon-button" disabled={busy} aria-label={`${item.name} 이름 바꾸기`} onClick={() => edit(item, 'rename')}><Pencil aria-hidden="true" size={16} /></button><button className="icon-button danger-text" disabled={busy} aria-label={`${item.name} 삭제`} onClick={() => edit(item, 'delete')}><Trash2 aria-hidden="true" size={16} /></button></div>
      </div>)}</div>
      {!s.buildings.length && <Empty title="관리 중인 건물이 없습니다">새 건물을 추가하거나 삭제한 건물을 복구해 주세요.</Empty>}
      <button className="button primary full building-add" disabled={busy} onClick={() => { setName(''); setTemplate('empty'); setView('add'); }}><Plus aria-hidden="true" size={17} />건물 추가</button>
      {!!s.deleted_buildings.length && <details className="deleted-buildings"><summary>최근 삭제한 건물 ({s.deleted_buildings.length})</summary><div>{s.deleted_buildings.map(item => <div key={item.id}><span><strong>{item.name}</strong><small>{item.floors}개 층 · 쓰레기통 {item.bin_count}개</small></span><button className="button secondary small" disabled={busy} onClick={async () => { if (await action(`/buildings/${item.id}/restore`, {}, 'POST', '건물을 복구했습니다.')) onSelected(); }}><RotateCcw aria-hidden="true" size={14} />복구</button></div>)}</div></details>}
    </> : view === 'add' ? <form className="building-create-form" onSubmit={async e => { e.preventDefault(); if (await action('/buildings', { name: name.trim(), template, ...(template === 'empty' ? { floors } : {}) }, 'POST', '새 건물을 추가했습니다.')) onSelected(); }}>
      <label>건물 이름<input ref={nameInput} required maxLength={80} value={name} onChange={e => setName(e.target.value)} placeholder="예: 정석학술정보관" /></label>
      <label>시작할 데이터<select value={template} onChange={e => setTemplate(e.target.value)}>{templates.map(t => <option key={t.id} value={t.id}>{t.title}</option>)}</select><small>{templates.find(t => t.id === template)?.detail}</small></label>
      {template === 'empty' && <label>층수<input type="number" min="1" max="10" required value={floors} onChange={e => setFloors(Number(e.target.value))} /><small>실물 장치·관리자실·집하장 위치는 배치도에서 지정합니다.</small></label>}
      <p className="muted-note">새 건물을 만든 뒤 도면과 쓰레기통 위치를 등록하세요.</p>
      <div className="modal-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => setView('list')}>취소</button><button className="button primary" disabled={busy || !name.trim()}>{busy ? pending : <Plus aria-hidden="true" size={16} />}건물 만들기</button></div>
    </form> : view === 'rename' && target ? <form className="building-create-form" onSubmit={async e => { e.preventDefault(); if (await action(`/buildings/${target.id}`, { name: name.trim() }, 'PATCH', '건물 이름을 바꿨습니다.')) setView('list'); }}>
      <label>건물 이름<input ref={nameInput} required maxLength={80} value={name} onChange={e => setName(e.target.value)} /></label><div className="modal-actions"><button type="button" className="button secondary" disabled={busy} onClick={() => setView('list')}>취소</button><button className="button primary" disabled={busy || !name.trim()}>{busy ? pending : <Check aria-hidden="true" size={16} />}이름 저장</button></div>
    </form> : target ? <div className="building-delete-confirm"><strong>{target.name}</strong><p>이 건물의 배치·설정·수거 기록을 관리 목록에서 삭제합니다. ‘최근 삭제한 건물’에서 복구할 수 있습니다.</p><p className="muted-note">장치 연결 키는 만료됩니다. 복구 후 센서를 다시 연결하려면 새 키를 발급하세요.</p><div className="modal-actions"><button className="button secondary" disabled={busy} onClick={() => setView('list')}>취소</button><button className="button building-delete-button" disabled={busy} onClick={async () => { if (await action(`/buildings/${target.id}`, {}, 'DELETE', '건물을 삭제했습니다.')) setView('list'); }}>{busy ? pending : <Trash2 aria-hidden="true" size={16} />}건물 삭제</button></div></div> : null}
  </Dialog>;
}
