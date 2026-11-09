import PublicDemoNotice from './PublicDemoNotice';
import { floorLabel, floorCount } from './floors';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowRight, ArrowUpRight, Bell, Building2, Check, ChevronDown, ChevronRight, CircleHelp, Clock3, Database, LayoutDashboard, Leaf, Loader2, LogOut, MapPinned, Menu, Radio, Route as RouteIcon, Settings, ShieldCheck, Sparkles, Users, X, History, Wifi, AlertCircle, RefreshCw } from 'lucide-react';
import { api, compartmentName, compartments, payload, dateTime, fillText, sourceText, statusText, toEmpty, topCompartment } from './types';
import type { Bin, Fills, Page, Workspace, WorkspaceResponse } from './types';
import { Badge, BinArt, CompartmentRow, Dialog, Logo, SensorNotice } from './UI';
import { Dashboard, RoutePanel } from './Dashboard';
import { BuildingEditor, DevicePage, HistoryPage, SettingsPage, TeamPage } from './Pages';
import BuildingManager from './BuildingManager';
import { BinCompleteButton } from './CollectionActions';
import type { BuildingAction } from './BuildingManager';

export interface PageProps {
  s: Workspace; busy: boolean;
  mutate: (path: string, data?: unknown, method?: string, success?: string) => Promise<Workspace | null>;
  navigate: (page: Page) => void; openBin: (id: string) => void; notify: (text: string, kind?: 'success' | 'error') => void;
}
const navItems = [
  { id: 'dashboard' as Page, label: '대시보드', icon: LayoutDashboard },
  { id: 'map' as Page, label: '건물 · 배치도', icon: MapPinned },
  { id: 'team' as Page, label: '관리자 · 수거 동선', icon: Users },
  { id: 'history' as Page, label: '수거 기록', icon: History },
  { id: 'device' as Page, label: '장치 연동', icon: Radio },
];
const pageNames: Record<Page, string> = { dashboard: '대시보드', map: '건물 · 배치도', team: '관리자 · 수거 동선', history: '수거 기록', device: '장치 연동', settings: '설정' };
function initialPage(): Page { const value = location.hash.slice(1); return Object.hasOwn(pageNames, value) ? value as Page : 'dashboard'; }

function Auth({ onLogin }: { onLogin: () => Promise<void> }) {
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState(''); const [name, setName] = useState(''); const [password, setPassword] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(e?: FormEvent, demo = false) {
    e?.preventDefault(); setError(''); setBusy(true);
    try {
      await api(demo || !register ? '/auth/login' : '/auth/register', payload(demo ? { email: 'demo@reloop.local', password: 'Demo1234!' } : { email, password, ...(register ? { name } : {}) }));
      await onLogin();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="auth-page">
    <section className="auth-story"><Logo light /><div className="auth-story-body"><span className="auth-kicker"><i /> 스마트 분리수거 관리</span><h1>더 가벼운 수거,<br />더 나은 내일.</h1><p>쓰레기통의 상태부터 효율적인 수거 동선까지.<br />공간의 순환을 한눈에 관리하세요.</p>
      <div className="auth-illustration"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="auth-floor"><span className="floor-line one" /><span className="floor-line two" /><span className="floor-line three" /></div><div className="hero-bin one"><BinArt fill={45} status="normal" large /><span>01 <i /></span></div><div className="hero-bin two"><BinArt fill={94} status="critical" large /><span>02 <i /></span></div><div className="hero-bin three"><BinArt fill={82} status="warning" large /><span>03 <i /></span></div><div className="floating-metric"><span className="metric-icon"><RouteIcon aria-hidden="true" size={20} /></span><div><small>필요한 곳으로, 효율적으로</small><strong>스마트 수거 동선</strong></div><ArrowUpRight aria-hidden="true" size={17} /></div><div className="floating-leaf"><Leaf aria-hidden="true" size={25} /></div></div>
    </div><div className="auth-story-footer"><span>INLOOP · COMPETITION MVP</span><span>작은 변화가 만드는 큰 순환</span></div></section>
    <section className="auth-form-side"><div className="auth-top"><Logo onHome={() => { setRegister(false); setError(''); location.hash = 'dashboard'; }} /><span><Database aria-hidden="true" size={14} /> {window.inloopPublicDemo ? '이 브라우저에 체험 데이터 저장' : '로컬 서버에 안전하게 저장'}</span></div><div className="auth-form-wrap"><PublicDemoNotice /><span className="eyebrow">관리자 워크스페이스</span><h2>{register ? '관리자 계정 만들기' : '수거 관리를 시작하세요'}</h2><p>{register ? '관리자 계정을 만들고 나만의 건물을 관리하세요.' : '관리자 계정으로 로그인하고 수거 현황을 확인하세요.'}</p>
      <form onSubmit={submit} aria-busy={busy} aria-describedby={error ? "auth-error" : undefined}>{register && <label>관리자 이름<input required value={name} maxLength={40} onChange={e => setName(e.target.value)} placeholder="이름을 입력해 주세요" autoComplete="name" /></label>}<label>이메일<input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="name@example.com" autoComplete="username" aria-describedby={error ? "auth-error" : undefined} /></label><label>비밀번호<input type="password" required minLength={register ? 8 : 1} value={password} onChange={e => setPassword(e.target.value)} placeholder={register ? '8자 이상 입력해 주세요' : '비밀번호를 입력해 주세요'} autoComplete={register ? 'new-password' : 'current-password'} aria-describedby={error ? 'auth-error' : undefined} /></label>{error && <div className="form-error" id="auth-error" role="alert"><AlertCircle aria-hidden="true" size={16} />{error}</div>}<button className="button primary auth-submit" disabled={busy}>{busy ? <><Loader2 aria-hidden="true" className="spin" size={18} />연결 중…</> : <>{register ? '회원가입' : '로그인'}<ArrowRight aria-hidden="true" size={17} /></>}</button></form>
      <div className="auth-switch">{register ? '이미 계정이 있으신가요?' : '아직 계정이 없으신가요?'}<button onClick={() => { setRegister(!register); setError(''); }}>{register ? '로그인' : '회원가입'}</button></div>
      <div className="auth-divider"><span>대회 시연을 빠르게 시작하려면</span></div><button className="button demo-login" disabled={busy} onClick={() => submit(undefined, true)}><Sparkles aria-hidden="true" size={17} /> 시연 계정으로 둘러보기<ArrowUpRight aria-hidden="true" size={17} /></button><div className="auth-demo-note">시연 계정에 저장된 건물·배치·수거 기록을 불러옵니다.</div>
    </div><div className="auth-bottom"><ShieldCheck aria-hidden="true" size={15} /> {window.inloopPublicDemo ? '체험 계정과 데이터는 이 브라우저에만 저장됩니다.' : '계정과 건물 데이터는 이 서버에만 저장됩니다.'}</div></section>
  </div>;
}

function BinDetails({ bin, s, mutate, busy, onClose, navigate }: { bin: Bin; s: Workspace; mutate: PageProps['mutate']; busy: boolean; onClose: () => void; navigate: (p: Page) => void }) {
  const [name, setName] = useState(bin.name);
  const [nameError, setNameError] = useState('');
  useEffect(() => { setName(bin.name); setNameError(''); }, [bin.id, bin.name]);
  const saved = JSON.stringify(bin.compartments); // the workspace refresh replaces the object every 5 seconds
  const [fills, setFills] = useState<Fills>(bin.compartments);
  useEffect(() => setFills(JSON.parse(saved)), [bin.id, saved]);
  const top = topCompartment(bin.compartments);
  const emptied = toEmpty(bin.compartments, s.building);
  const route = s.last_plan && !s.last_plan.outdated ? s.last_plan.routes.find(r => r.bin_ids.includes(bin.id)) : undefined;
  const readings = s.readings.filter(r => r.bin_id === bin.id && r.fill !== null).slice(0, 12).reverse();
  return <Dialog title={bin.id} subtitle={`${floorLabel(bin.floor)} ${bin.name}`} onClose={onClose}>
    <form className="bin-name-form" onSubmit={async e => {
      e.preventDefault();
      if (!name.trim()) { setNameError('쓰레기통 이름을 입력해 주세요.'); return; }
      setNameError('');
      const result = await mutate(`/bins/${bin.id}`, { name: name.trim() }, 'PATCH', '쓰레기통 이름을 저장했습니다.');
      if (!result) setNameError('이름을 저장하지 못했습니다. 연결 상태를 확인한 뒤 다시 시도해 주세요.');
    }}>
      <label htmlFor="bin-name">쓰레기통 이름</label><div><input id="bin-name" value={name} onChange={e => { setName(e.target.value); setNameError(''); }} required maxLength={40} placeholder="예: 3층 서쪽 계단 앞" aria-invalid={!!nameError} aria-describedby={nameError ? 'bin-name-error' : 'bin-name-hint'} /><button className="button secondary" disabled={busy || name.trim() === bin.name || !name.trim()}>이름 저장</button></div>
      {nameError ? <p id="bin-name-error" className="form-error" role="alert">{nameError}</p> : <small id="bin-name-hint">최대 40자 · {bin.id} 번호와 연결된 센서는 그대로 유지됩니다.</small>}
    </form>
    <div className="bin-detail-hero"><BinArt fill={bin.fill} status={bin.status} large /><div><Badge status={bin.status} /><div className="detail-fill">{bin.fill === null ? '—' : Math.round(bin.fill)}{bin.fill !== null && <small>%</small>}</div><span className="source-label">{top ? `가장 찬 칸 ${compartmentName[top]} · ` : ''}{sourceText[bin.reading_source]}</span></div></div>
    <CompartmentRow values={bin.compartments} building={s.building} large /><SensorNotice bin={bin} details />
    <div className="detail-info"><div><span>마지막 측정</span><strong>{dateTime(bin.measured_at)}</strong></div><div><span>담당 관리자</span><strong>{route ? `관리자 ${route.worker}` : '경로 배정 전'}</strong></div><div><span>수거 기준</span><strong>칸별 {s.building.critical_threshold}% 이상</strong></div></div>
    {bin.device_type === 'demo' ? <div className="detail-slider"><div><strong>더미 적재율 조절</strong><span>칸별</span></div>{compartments.map(c => <label key={c} className="compartment-slider"><span>{compartmentName[c]}</span><input type="range" min="0" max="100" value={fills[c] ?? 0} onChange={e => setFills({ ...fills, [c]: +e.target.value })} aria-label={`${compartmentName[c]} 칸 더미 적재율`} /><b>{fills[c] ?? 0}%</b></label>)}<button className="button secondary full" disabled={busy || JSON.stringify(fills) === saved} onClick={() => mutate(`/bins/${bin.id}`, { fills }, 'PATCH', '적재율이 변경되었습니다.')}>적재율 적용</button></div> : <div className="notice"><Radio aria-hidden="true" size={17} /><div>{bin.reading_source === 'actual' ? '실물 센서에서 수신한 값입니다. 수거 완료 후 다음 센서값으로 비워진 상태를 확인합니다.' : '장치 연동 화면에서 센서를 연결하거나 시뮬레이션으로 상태 변화를 확인할 수 있습니다.'}<button className="text-link" onClick={() => { onClose(); navigate('device'); }}>장치 연동 열기<ArrowUpRight aria-hidden="true" size={14} /></button></div></div>}
    {readings.length > 1 && <div className="reading-spark"><span>최근 수신 추이</span><svg viewBox="0 0 400 90" role="img" aria-label="최근 적재율 추이"><path d="M 0 80 H 400 M 0 40 H 400" stroke="#e8ede7" strokeDasharray="4 4" /><polyline points={readings.map((r, i) => `${i * 400 / (readings.length - 1)},${80 - (r.fill ?? 0) * .7}`).join(' ')} stroke="#508264" fill="none" strokeWidth="3" /></svg></div>}
    {bin.fill !== null && bin.fill > 0 && <p className="muted-note empty-note">수거 완료 시 비우는 칸: {fillText(emptied)}</p>}
    <div className="modal-actions"><button className="button secondary" onClick={onClose}>닫기</button><BinCompleteButton s={s} bin={bin} mutate={mutate} busy={busy} onComplete={onClose} /></div>
  </Dialog>;
}

export default function App() {
  const [s, setS] = useState<WorkspaceResponse | null>(null); const [loading, setLoading] = useState(true);
  const [buildingsOpen, setBuildingsOpen] = useState(false);
  const [page, setPage] = useState<Page>(initialPage); const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [offline, setOffline] = useState(false); const [startError, setStartError] = useState('');
  const [toast, setToast] = useState<{ text: string; kind: 'success' | 'error' } | null>(null);
  const [selectedBin, setSelectedBin] = useState<string | null>(null); const [menu, setMenu] = useState(false);
  const [alerts, setAlerts] = useState(false); const [guide, setGuide] = useState(false);
  const epoch = useRef(0); const busyRef = useRef(false); const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const notify = useCallback((text: string, kind: 'success' | 'error' = 'success') => {
    setToast({ text, kind }); clearTimeout(toastTimer.current); toastTimer.current = setTimeout(() => setToast(null), 4500);
  }, []);
  const load = useCallback(async () => {
    const captured = ++epoch.current;
    try { const next = await api<WorkspaceResponse>('/workspace'); if (captured !== epoch.current) return; setS(next); setOffline(false); setStartError(''); setActionError(''); }
    catch (e) { if (captured !== epoch.current) return; if ((e as { status: number }).status === 401) setS(null); else setStartError('로컬 서버에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); const handler = () => setPage(initialPage()); window.addEventListener('hashchange', handler); return () => window.removeEventListener('hashchange', handler); }, [load]);
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }); }, [s?.user.id]);
  useEffect(() => { setSelectedBin(null); setAlerts(false); }, [s?.workspace_id]);
  useEffect(() => {
    if (!s?.user.id) return;
    const timer = setInterval(async () => {
      if (busyRef.current || document.visibilityState === 'hidden') return;
      const captured = epoch.current;
      try { const next = await api<WorkspaceResponse>('/workspace', { headers: s.workspace_id ? { 'X-Building-ID': String(s.workspace_id) } : {} }); if (captured === epoch.current) { setS(next); setOffline(false); } }
      catch (e) { if (captured !== epoch.current) return; if ((e as { status: number }).status === 401) setS(null); else if ((e as { status: number }).status === 404) load(); else setOffline(true); }
    }, 5000);
    return () => clearInterval(timer);
  }, [s?.user.id, s?.workspace_id, load]);
  const mutate: PageProps['mutate'] = async (path, data = {}, method = 'POST', success) => {
    if (busyRef.current || !s?.workspace_id) return null;
    busyRef.current = true; setBusy(true); setActionError(''); const captured = ++epoch.current;
    try { const next = await api<Workspace>(path, { method, body: JSON.stringify(data), headers: { 'X-Building-ID': String(s.workspace_id) } }); if (captured !== epoch.current) return null; setS(next); setOffline(false); if (success) notify(success); return next; }
    catch (e) { if (captured !== epoch.current) return null; setActionError((e as Error).message); notify((e as Error).message, 'error'); if ((e as { status: number }).status === 401) setS(null); return null; }
    finally { busyRef.current = false; setBusy(false); }
  };
  const manageBuildings: BuildingAction = async (path, data = {}, method = 'POST', message) => {
    if (busyRef.current) return false;
    busyRef.current = true; setBusy(true); setActionError(''); const captured = ++epoch.current;
    try {
      const next = await api<WorkspaceResponse>(path, { method, body: JSON.stringify(data), headers: s?.workspace_id ? { 'X-Building-ID': String(s.workspace_id) } : {} });
      if (captured !== epoch.current) return false;
      setS(next); setOffline(false); setSelectedBin(null); if (message) notify(message); return true;
    } catch (error) { if (captured !== epoch.current) return false; setActionError((error as Error).message); notify((error as Error).message, 'error'); return false; }
    finally { busyRef.current = false; setBusy(false); }
  };
  function navigate(next: Page) { setPage(next); location.hash = next; setMenu(false); setAlerts(false); window.scrollTo({ top: 0, behavior: 'instant' }); requestAnimationFrame(() => document.getElementById('main-content')?.focus({ preventScroll: true })); }
  async function logout() { try { await api('/auth/logout', payload({})); epoch.current++; setS(null); setSelectedBin(null); setBuildingsOpen(false); } catch (e) { notify((e as Error).message, 'error'); } }
  if (loading) return <div className="loading-page" role="status" aria-live="polite"><Logo /><Loader2 aria-hidden="true" className="spin" /><span>건물 정보를 불러오고 있습니다.</span></div>;
  if (!s) return startError ? <div className="loading-page" role="alert"><Logo /><AlertCircle aria-hidden="true" size={30} /><p>{startError}</p><button className="button primary" onClick={load}><RefreshCw aria-hidden="true" size={16} /> 다시 연결</button></div> : <Auth onLogin={load} />;
  const toastElement = (toast && <div className={`toast ${toast.kind}`} role={toast.kind === 'error' ? 'alert' : 'status'}>{toast.kind === 'success' ? <Check aria-hidden="true" size={18} /> : <AlertCircle aria-hidden="true" size={18} />}<span>{toast.text}</span><button onClick={() => setToast(null)} aria-label="알림 닫기"><X aria-hidden="true" size={15} /></button></div>);
  const buildingPanel = buildingsOpen && <BuildingManager s={s} busy={busy} error={actionError} action={manageBuildings} onClose={() => setBuildingsOpen(false)} onSelected={() => { setBuildingsOpen(false); navigate('map'); }} />;
  if (!s.building) return <div className="no-buildings-page"><header><Logo /><button className="button secondary" onClick={logout}><LogOut aria-hidden="true" size={16} />로그아웃</button></header><main id="main-content" tabIndex={-1}><PublicDemoNotice /><span className="no-buildings-icon"><Building2 aria-hidden="true" size={38} /></span><h1>관리할 건물을 추가해 주세요</h1><p>건물별로 도면·쓰레기통·관리자·수거 기록을 저장합니다.</p><button className="button primary" onClick={() => setBuildingsOpen(true)}>건물 추가 · 관리<ArrowRight aria-hidden="true" size={16} /></button>{s.deleted_buildings.length > 0 && <small>최근 삭제한 건물 {s.deleted_buildings.length}개도 복구할 수 있습니다.</small>}</main>{buildingPanel}{toastElement}</div>;
  const critical = s.bins.filter(b => b.status === 'critical');
  const bin = s.bins.find(b => b.id === selectedBin);
  const props: PageProps = { s, busy, mutate, navigate, openBin: setSelectedBin, notify };
  const CurrentPage = { dashboard: Dashboard, map: BuildingEditor, team: TeamPage, history: HistoryPage, device: DevicePage, settings: SettingsPage }[page];
  return <div className="app-shell"><a className="skip-link" href="#main-content" onClick={e => { e.preventDefault(); document.getElementById('main-content')?.focus(); }}>본문으로 바로가기</a>

    <aside className="sidebar" aria-label="워크스페이스 메뉴"><Logo onHome={() => navigate('dashboard')} /><div className="workspace-label">관리 중인 건물 <b>{s.buildings.length}개</b></div><button className="building-switch" aria-label={`건물 관리 · ${s.buildings.length}개 · 현재 ${s.building.name}`} aria-haspopup="dialog" disabled={busy} onClick={() => { setActionError(''); setBuildingsOpen(true); }}><span className="building-switch-icon"><Building2 aria-hidden="true" size={18} /></span><span><strong>{s.building.name.split('·')[1]?.trim() || s.building.name}</strong><small>{floorCount(s.building)}개 층 · 건물 선택 / 추가</small></span><ChevronDown aria-hidden="true" size={14} /></button>
      <div className="nav-label">관리 메뉴</div><nav aria-label="주 메뉴">{navItems.map(item => <button key={item.id} aria-current={page === item.id ? "page" : undefined} className={page === item.id ? 'active' : ''} onClick={() => navigate(item.id)}><item.icon aria-hidden="true" size={19} strokeWidth={1.7} /><span>{item.label}</span>{item.id === 'dashboard' && critical.length > 0 && <i className="nav-count">{critical.length}</i>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="local-card"><span className="local-card-icon"><Leaf aria-hidden="true" size={20} /></span><strong>상태에서 동선까지</strong><p>센서로 확인하고,<br />필요한 곳부터 수거하세요.</p><div><i /> 대회 시연용 MVP</div></div><button className={`settings-nav ${page === 'settings' ? 'active' : ''}`} onClick={() => navigate('settings')}><Settings aria-hidden="true" size={19} /> 설정</button><div className="sidebar-footer"><i className={offline ? 'offline' : ''} />{offline ? '연결 확인 필요' : window.inloopPublicDemo ? '브라우저 체험' : '로컬 서버 연결됨'}<span>v1.0</span></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" onClick={() => setMenu(true)} aria-expanded={menu} aria-haspopup="dialog" aria-label="메뉴 열기"><Menu aria-hidden="true" size={20} /></button><a className="home-brand-link" href="#dashboard" aria-label="inloop 홈으로 이동" onClick={e => { e.preventDefault(); navigate('dashboard'); }}>inloop</a><ChevronRight aria-hidden="true" size={13} /><strong>{pageNames[page]}</strong></div><div className="topbar-actions"><span className="saved-label"><Check aria-hidden="true" size={13} />{busy ? '저장 중' : window.inloopPublicDemo ? '체험 저장' : '로컬 저장'}</span><button className="icon-button help-button" aria-label="시연 가이드" onClick={() => setGuide(true)}><CircleHelp aria-hidden="true" size={19} /></button><div className="alert-anchor"><button className="icon-button" aria-label={`수거 알림 ${critical.length}개`} aria-haspopup="dialog" onClick={() => setAlerts(true)}><Bell aria-hidden="true" size={19} />{critical.length > 0 && <i className="notification-dot" />}</button></div><div className="topbar-divider" /><span className="user-avatar">{s.user.name.slice(0, 1)}</span><div className="user-label"><strong>{s.user.name}</strong><small>시설 관리자</small></div><button className="icon-button logout-button" onClick={logout} aria-label="로그아웃"><LogOut aria-hidden="true" size={16} /></button></div></header>
    {offline && <div className="offline-banner" role="alert"><Wifi aria-hidden="true" size={16} /> 서버 연결이 끊겼습니다. 화면에는 마지막으로 받은 정보가 표시됩니다.<button onClick={load}>다시 연결</button></div>}
    <main className="main-content" id="main-content" tabIndex={-1}><PublicDemoNotice />{actionError && <div className="action-error" role="alert"><AlertCircle aria-hidden="true" size={19} /><div><strong>작업을 완료하지 못했습니다</strong><p>{actionError}</p><button className="text-link" disabled={busy} onClick={load}>최신 정보 다시 불러오기<RefreshCw aria-hidden="true" size={14} /></button></div><button className="icon-button" aria-label="작업 오류 안내 닫기" onClick={() => setActionError('')}><X aria-hidden="true" size={16} /></button></div>}<CurrentPage key={s.workspace_id} {...props} />
    <footer className="page-footer"><span>inloop. <i /> 스마트 분리수거 관리 시스템</span><span><Database aria-hidden="true" size={12} /> {window.inloopPublicDemo ? '이 브라우저에 체험 데이터가 저장됩니다' : '이 기기의 로컬 서버에 저장됩니다'}</span></footer></main></div>
    {toastElement}
    {menu && <Dialog title="관리 메뉴" subtitle={s.building.name} onClose={() => setMenu(false)}><nav className="mobile-navigation" aria-label="모바일 주 메뉴"><button disabled={busy} onClick={() => { setMenu(false); setActionError(''); setBuildingsOpen(true); }}><Building2 aria-hidden="true" size={20} /><span>건물 관리 · {s.buildings.length}개<small>{s.building.name}</small></span><ChevronRight aria-hidden="true" size={16} /></button>{navItems.map(item => <button key={item.id} aria-current={page === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><item.icon aria-hidden="true" size={20} /><span>{item.label}</span><ChevronRight aria-hidden="true" size={16} /></button>)}<button aria-current={page === 'settings' ? 'page' : undefined} onClick={() => navigate('settings')}><Settings aria-hidden="true" size={20} /><span>설정</span><ChevronRight aria-hidden="true" size={16} /></button></nav></Dialog>}
    {alerts && <Dialog title="수거 알림" subtitle={critical.length ? `수거가 필요한 쓰레기통 ${critical.length}개` : '현재 수거가 필요한 쓰레기통이 없습니다.'} onClose={() => setAlerts(false)}><div className="alert-list">{critical.map(b => <button key={b.id} onClick={() => { setAlerts(false); setSelectedBin(b.id); }}><span className="alert-small-dot" /><span><strong>{b.id}</strong><small>{b.floor}층 {b.name}</small></span><b>{b.fill}%</b><ChevronRight aria-hidden="true" size={16} /></button>)}</div><div className="modal-actions"><button className="button secondary" onClick={() => setAlerts(false)}>닫기</button></div></Dialog>}
    {buildingPanel}
    {bin && <BinDetails bin={bin} s={s} mutate={mutate} busy={busy} navigate={navigate} onClose={() => setSelectedBin(null)} />}
    {guide && <Dialog title="3분이면 충분한 inloop 시연" subtitle="실물 1대와 3층 예시 건물로 수거 흐름을 보여 주세요." onClose={() => setGuide(false)}><div className="guide-steps">{[['상태 확인', '번호와 색상으로 층별 쓰레기통의 적재율을 확인합니다.'], ['주황색 포함 선택', '주의 상태까지 함께 수거할지 선택합니다.'], ['관리자 인원 비교', '수거 가능 인원을 1명에서 3명으로 바꾸어 업무 배분을 비교합니다.'], ['실물 센서 연결', '장치 연동에서 연결 키를 발급하고 실제 측정값을 전송합니다. 연결 전에는 시뮬레이션도 가능합니다.'], ['수거 완료', '카드 또는 경로에서 수거 완료를 누르고 기록을 확인합니다.']].map(([title, desc], i) => <div key={title}><span>{i + 1}</span><div><strong>{title}</strong><p>{desc}</p></div></div>)}</div><div className="notice"><Clock3 aria-hidden="true" size={17} /><span>예상 시간은 이동 거리와 설정된 수거 시간을 합산한 시연용 추정치입니다.</span></div><div className="modal-actions"><button className="button primary" onClick={() => setGuide(false)}>시연 시작하기<ArrowRight aria-hidden="true" size={16} /></button></div></Dialog>}
  </div>;
}
