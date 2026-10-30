import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowRight, ArrowUpRight, Bell, Building2, Check, ChevronDown, ChevronRight, CircleHelp, Clock3, Database, LayoutDashboard, Leaf, Loader2, LogOut, MapPinned, Menu, Radio, Route as RouteIcon, Settings, ShieldCheck, Sparkles, Users, X, History, Wifi, AlertCircle, RefreshCw } from 'lucide-react';
import { api, payload, dateTime, sourceText, statusText } from './types';
import type { Bin, Page, Workspace } from './types';
import { Badge, BinArt, Dialog, Logo } from './UI';
import { Dashboard, RoutePanel } from './Dashboard';
import { BuildingEditor, DevicePage, HistoryPage, SettingsPage, TeamPage } from './Pages';

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
    <section className="auth-story"><Logo light /><div className="auth-story-body"><span className="auth-kicker"><i /> SMART RECYCLING MANAGEMENT</span><h1>더 가벼운 수거,<br />더 나은 내일.</h1><p>쓰레기통의 상태부터 효율적인 수거 동선까지.<br />공간의 순환을 한눈에 관리하세요.</p>
      <div className="auth-illustration"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="auth-floor"><span className="floor-line one" /><span className="floor-line two" /><span className="floor-line three" /></div><div className="hero-bin one"><BinArt fill={45} status="normal" large /><span>01 <i /></span></div><div className="hero-bin two"><BinArt fill={94} status="critical" large /><span>02 <i /></span></div><div className="hero-bin three"><BinArt fill={82} status="warning" large /><span>03 <i /></span></div><div className="floating-metric"><span className="metric-icon"><RouteIcon size={20} /></span><div><small>필요한 곳으로, 효율적으로</small><strong>스마트 수거 동선</strong></div><ArrowUpRight size={17} /></div><div className="floating-leaf"><Leaf size={25} /></div></div>
    </div><div className="auth-story-footer"><span>RELOOP · COMPETITION MVP</span><span>작은 변화가 만드는 큰 순환</span></div></section>
    <section className="auth-form-side"><div className="auth-top"><span><Database size={14} /> 로컬 서버에 안전하게 저장</span></div><div className="auth-form-wrap"><span className="eyebrow">WELCOME TO RELOOP</span><h2>{register ? '함께, 더 나은 순환을.' : '다시 만나 반갑습니다.'}</h2><p>{register ? '관리자 계정을 만들고 나만의 건물을 관리하세요.' : '관리자 계정으로 로그인하고 수거 현황을 확인하세요.'}</p>
      <form onSubmit={submit}>{register && <label>관리자 이름<input required value={name} maxLength={40} onChange={e => setName(e.target.value)} placeholder="이름을 입력해 주세요" autoComplete="name" /></label>}<label>이메일<input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="name@example.com" autoComplete="username" /></label><label>비밀번호<input type="password" required minLength={register ? 8 : 1} value={password} onChange={e => setPassword(e.target.value)} placeholder={register ? '8자 이상 입력해 주세요' : '비밀번호를 입력해 주세요'} autoComplete={register ? 'new-password' : 'current-password'} /></label>{error && <div className="form-error" role="alert"><AlertCircle size={16} />{error}</div>}<button className="button primary auth-submit" disabled={busy}>{busy ? <Loader2 className="spin" size={18} /> : <>{register ? '회원가입' : '로그인'}<ArrowRight size={17} /></>}</button></form>
      <div className="auth-switch">{register ? '이미 계정이 있으신가요?' : '아직 계정이 없으신가요?'}<button onClick={() => { setRegister(!register); setError(''); }}>{register ? '로그인' : '회원가입'}</button></div>
      <div className="auth-divider"><span>대회 시연을 빠르게 시작하려면</span></div><button className="button demo-login" disabled={busy} onClick={() => submit(undefined, true)}><Sparkles size={17} /> 시연 계정으로 둘러보기<ArrowUpRight size={17} /></button><div className="auth-demo-note">3층 예시 건물 · 쓰레기통 12개 · 관리자 3명</div>
    </div><div className="auth-bottom"><ShieldCheck size={15} /> 계정과 건물 데이터는 이 서버에만 저장됩니다.</div></section>
  </div>;
}

function BinDetails({ bin, s, mutate, busy, onClose, navigate }: { bin: Bin; s: Workspace; mutate: PageProps['mutate']; busy: boolean; onClose: () => void; navigate: (p: Page) => void }) {
  const [fill, setFill] = useState(bin.fill ?? 0);
  useEffect(() => setFill(bin.fill ?? 0), [bin.id, bin.fill]);
  const route = s.last_plan?.routes.find(r => r.bin_ids.includes(bin.id));
  const readings = s.readings.filter(r => r.bin_id === bin.id && r.fill !== null).slice(0, 12).reverse();
  return <Dialog title={bin.id} subtitle={`${bin.floor}층 ${bin.name} · ${bin.category}`} onClose={onClose}>
    <div className="bin-detail-hero"><BinArt fill={bin.fill} status={bin.status} large /><div><Badge status={bin.status} /><div className="detail-fill">{bin.fill === null ? '—' : Math.round(bin.fill)}<small>%</small></div><span className="source-label">{sourceText[bin.reading_source]}</span></div></div>
    <div className="detail-info"><div><span>마지막 측정</span><strong>{dateTime(bin.measured_at)}</strong></div><div><span>담당 관리자</span><strong>{route ? `관리자 ${route.worker}` : '경로 배정 전'}</strong></div><div><span>수거 기준</span><strong>{s.building.critical_threshold}% 이상</strong></div></div>
    {bin.device_type === 'demo' ? <div className="detail-slider"><div><strong>더미 적재율 조절</strong><span>{fill}%</span></div><input type="range" min="0" max="100" value={fill} onChange={e => setFill(+e.target.value)} aria-label="더미 적재율" /><div className="range-labels"><span>비어 있음</span><span>가득 참</span></div><button className="button secondary full" disabled={busy || fill === bin.fill} onClick={() => mutate(`/bins/${bin.id}`, { fill }, 'PATCH', '적재율이 변경되었습니다.')}>적재율 적용</button></div> : <div className="notice"><Radio size={17} /><div>{bin.reading_source === 'actual' ? '실물 센서에서 수신한 값입니다. 수거 완료 후 다음 센서값으로 비워진 상태를 확인합니다.' : '장치 연동 화면에서 센서를 연결하거나 시뮬레이션으로 상태 변화를 확인할 수 있습니다.'}<button className="text-link" onClick={() => { onClose(); navigate('device'); }}>장치 연동 열기<ArrowUpRight size={14} /></button></div></div>}
    {readings.length > 1 && <div className="reading-spark"><span>최근 수신 추이</span><svg viewBox="0 0 400 90" role="img" aria-label="최근 적재율 추이"><path d="M 0 80 H 400 M 0 40 H 400" stroke="#e8ede7" strokeDasharray="4 4" /><polyline points={readings.map((r, i) => `${i * 400 / (readings.length - 1)},${80 - (r.fill ?? 0) * .7}`).join(' ')} stroke="#508264" fill="none" strokeWidth="3" /></svg></div>}
    <div className="modal-actions"><button className="button secondary" onClick={onClose}>닫기</button><button className="button primary" disabled={busy || bin.fill === null || bin.awaiting_confirmation || bin.status === 'offline' || bin.fill === 0} onClick={async () => { const result = await mutate(`/collect/${bin.id}`, { worker: route?.worker ?? null }, 'POST', '수거 완료를 기록했습니다.'); if (result) onClose(); }}><Check size={16} /> 수거 완료</button></div>
  </Dialog>;
}

export default function App() {
  const [s, setS] = useState<Workspace | null>(null); const [loading, setLoading] = useState(true);
  const [page, setPage] = useState<Page>(initialPage); const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false); const [startError, setStartError] = useState('');
  const [toast, setToast] = useState<{ text: string; kind: 'success' | 'error' } | null>(null);
  const [selectedBin, setSelectedBin] = useState<string | null>(null); const [menu, setMenu] = useState(false);
  const [alerts, setAlerts] = useState(false); const [guide, setGuide] = useState(false);
  const epoch = useRef(0); const busyRef = useRef(false); const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const notify = useCallback((text: string, kind: 'success' | 'error' = 'success') => {
    setToast({ text, kind }); clearTimeout(toastTimer.current); toastTimer.current = setTimeout(() => setToast(null), 4500);
  }, []);
  const load = useCallback(async () => {
    try { setS(await api<Workspace>('/workspace')); setOffline(false); setStartError(''); }
    catch (e) { if ((e as { status: number }).status === 401) setS(null); else setStartError('로컬 서버에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); const handler = () => setPage(initialPage()); window.addEventListener('hashchange', handler); return () => window.removeEventListener('hashchange', handler); }, [load]);
  useEffect(() => {
    if (!s?.user.id) return;
    const timer = setInterval(async () => {
      if (busyRef.current || document.visibilityState === 'hidden') return;
      const captured = epoch.current;
      try { const next = await api<Workspace>('/workspace'); if (captured === epoch.current) { setS(next); setOffline(false); } }
      catch (e) { if ((e as { status: number }).status === 401) setS(null); else setOffline(true); }
    }, 5000);
    return () => clearInterval(timer);
  }, [s?.user.id]);
  const mutate: PageProps['mutate'] = async (path, data = {}, method = 'POST', success) => {
    if (busyRef.current) return null;
    busyRef.current = true; setBusy(true); epoch.current++;
    try { const next = await api<Workspace>(path, { method, body: JSON.stringify(data) }); setS(next); setOffline(false); if (success) notify(success); return next; }
    catch (e) { notify((e as Error).message, 'error'); if ((e as { status: number }).status === 401) setS(null); return null; }
    finally { busyRef.current = false; setBusy(false); }
  };
  function navigate(next: Page) { setPage(next); location.hash = next; setMenu(false); setAlerts(false); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  async function logout() { try { await api('/auth/logout', payload({})); epoch.current++; setS(null); setSelectedBin(null); } catch (e) { notify((e as Error).message, 'error'); } }
  if (loading) return <div className="loading-page"><Logo /><Loader2 className="spin" /><span>건물 정보를 불러오고 있습니다.</span></div>;
  if (!s) return startError ? <div className="loading-page"><Logo /><AlertCircle size={30} /><p>{startError}</p><button className="button primary" onClick={load}><RefreshCw size={16} /> 다시 연결</button></div> : <Auth onLogin={load} />;
  const critical = s.bins.filter(b => b.status === 'critical');
  const bin = s.bins.find(b => b.id === selectedBin);
  const props: PageProps = { s, busy, mutate, navigate, openBin: setSelectedBin, notify };
  return <div className="app-shell">
    {menu && <div className="sidebar-overlay" onClick={() => setMenu(false)} />}
    <aside className={`sidebar ${menu ? 'open' : ''}`}><Logo /><div className="workspace-label">WORKSPACE</div><button className="building-switch" onClick={() => navigate('map')}><span className="building-switch-icon"><Building2 size={18} /></span><span><strong>{s.building.name.split('·')[1]?.trim() || s.building.name}</strong><small>{s.building.floors}개 층 · 로컬 워크스페이스</small></span><ChevronDown size={14} /></button>
      <div className="nav-label">관리 메뉴</div><nav>{navItems.map(item => <button key={item.id} className={page === item.id ? 'active' : ''} onClick={() => navigate(item.id)}><item.icon size={19} strokeWidth={1.7} /><span>{item.label}</span>{item.id === 'dashboard' && critical.length > 0 && <i className="nav-count">{critical.length}</i>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="local-card"><span className="local-card-icon"><Leaf size={19} /></span><strong>필요한 곳부터, 가볍게.</strong><p>작은 순환이 모여<br />더 나은 공간을 만듭니다.</p><div><i /> COMPETITION MVP</div></div><button className={`settings-nav ${page === 'settings' ? 'active' : ''}`} onClick={() => navigate('settings')}><Settings size={19} /> 설정</button><div className="sidebar-footer"><i className={offline ? 'offline' : ''} />{offline ? '서버 연결 확인 필요' : '로컬 서버 연결됨'}<span>v1.0</span></div></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" onClick={() => setMenu(!menu)} aria-label="메뉴 열기"><Menu size={20} /></button><span>워크스페이스</span><ChevronRight size={13} /><strong>{pageNames[page]}</strong></div><div className="topbar-actions"><span className="saved-label"><Check size={13} />{busy ? '저장 중' : '로컬 저장'}</span><button className="icon-button help-button" aria-label="시연 가이드" onClick={() => setGuide(true)}><CircleHelp size={19} /></button><div className="alert-anchor"><button className="icon-button" aria-label="수거 알림" onClick={() => setAlerts(!alerts)}><Bell size={19} />{critical.length > 0 && <i className="notification-dot" />}</button>{alerts && <div className="alert-popover"><strong>수거가 필요한 쓰레기통 <span>{critical.length}</span></strong>{critical.length ? critical.map(b => <button key={b.id} onClick={() => { setSelectedBin(b.id); setAlerts(false); }}><span className="alert-small-dot" /><span>{b.id}<small>{b.floor}층 {b.name}</small></span><b>{b.fill}%</b></button>) : <p>지금은 수거가 필요한 쓰레기통이 없습니다.</p>}</div>}</div><div className="topbar-divider" /><span className="user-avatar">{s.user.name.slice(0, 1)}</span><div className="user-label"><strong>{s.user.name}</strong><small>시설 관리자</small></div><button className="icon-button logout-button" onClick={logout} aria-label="로그아웃"><LogOut size={16} /></button></div></header>
    {offline && <div className="offline-banner" role="alert"><Wifi size={16} /> 서버 연결이 끊겼습니다. 화면에는 마지막으로 받은 정보가 표시됩니다.<button onClick={load}>다시 연결</button></div>}
    <main className="main-content">{page === 'dashboard' ? <Dashboard {...props} /> : page === 'map' ? <BuildingEditor {...props} /> : page === 'team' ? <TeamPage {...props} /> : page === 'history' ? <HistoryPage {...props} /> : page === 'device' ? <DevicePage {...props} /> : <SettingsPage {...props} />}
    <footer className="page-footer"><span>reloop. <i /> 스마트 분리수거 관리 시스템</span><span><Database size={12} /> 이 기기의 로컬 서버에 저장됩니다</span></footer></main></div>
    {toast && <div className={`toast ${toast.kind}`} role="status">{toast.kind === 'success' ? <Check size={18} /> : <AlertCircle size={18} />}<span>{toast.text}</span><button onClick={() => setToast(null)} aria-label="알림 닫기"><X size={15} /></button></div>}
    {bin && <BinDetails bin={bin} s={s} mutate={mutate} busy={busy} navigate={navigate} onClose={() => setSelectedBin(null)} />}
    {guide && <Dialog title="3분이면 충분한 리루프 시연" subtitle="실물 1대와 3층 예시 건물로 수거 흐름을 보여 주세요." onClose={() => setGuide(false)}><div className="guide-steps">{[['상태 확인', '번호와 색상으로 층별 쓰레기통의 적재율을 확인합니다.'], ['주황색 포함 선택', '주의 상태까지 함께 수거할지 선택합니다.'], ['관리자 인원 비교', '수거 가능 인원을 1명에서 3명으로 바꾸어 업무 배분을 비교합니다.'], ['실물 센서 연결', '장치 연동에서 연결 키를 발급하고 실제 측정값을 전송합니다. 연결 전에는 시뮬레이션도 가능합니다.'], ['수거 완료', '카드 또는 경로에서 수거 완료를 누르고 기록을 확인합니다.']].map(([title, desc], i) => <div key={title}><span>{i + 1}</span><div><strong>{title}</strong><p>{desc}</p></div></div>)}</div><div className="notice"><Clock3 size={17} /><span>예상 시간은 이동 거리와 설정된 수거 시간을 합산한 시연용 추정치입니다.</span></div><div className="modal-actions"><button className="button primary" onClick={() => setGuide(false)}>시연 시작하기<ArrowRight size={16} /></button></div></Dialog>}
  </div>;
}
