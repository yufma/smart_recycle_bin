import { Fragment, useEffect, useId, useRef, useState } from 'react';
import { AlertCircle, ArrowDown, ArrowRight, ArrowUp, ArrowUpRight, Building2, Check, ChevronDown, Clock3, Footprints, Home, Layers3, Loader2, MapPin, Minus, Plus, Radio, Recycle, RefreshCw, Route as RouteIcon, Sparkles, Trash2, Users } from 'lucide-react';
import type { PageProps } from './App';
import type { Route, RouteMode, Status } from './types';
import { compartmentName, dateTime, duration, fillText, sourceText, statusColor, statusText, topCompartment } from './types';
import { Badge, BinArt, ColorDot, CompartmentRow, Empty, FloorTabs, MiniLink, SectionTitle, SensorNotice, Toggle } from './UI';
import MapView from './MapView';

const routeModes: { id: RouteMode; title: string; desc: string }[] = [
  { id: 'fastest', title: '빨리 끝내기', desc: '마지막 관리자가 일을 마치는 시각을 가장 앞당깁니다.' },
  { id: 'lean', title: '인력 아끼기', desc: '한 사람 작업 시간 상한 안에서 가장 적은 인원으로, 그중 가장 빨리 끝나게 돕니다.' },
];

// Floor changes on the way to each next stop of the sequence (bins and unloading stops, ending at
// the drop-off point): moves[0] leads from the office to the first stop.
function floorMoves(route: Route, stops: string[], labels: Map<string, string>) {
  const moves: { from: number; to: number; via: string }[][] = stops.map(() => []);
  let leg = 0;
  route.path.forEach((p, i) => {
    const prev = route.path[i - 1];
    if (prev && prev.floor !== p.floor && leg < moves.length) {
      const via = labels.get(p.id) ?? (p.kind === 'elevator' ? '엘리베이터' : '계단');
      const last = moves[leg][moves[leg].length - 1];
      if (last && last.to === prev.floor && last.via === via) last.to = p.floor;
      else moves[leg].push({ from: prev.floor, to: p.floor, via });
    }
    if (i > 0 && p.id === stops[leg]) leg++;
  });
  return moves;
}

export function RoutePanel({ s, mutate, busy, openBin, navigate }: PageProps) {
  const modeGroup = useId();
  const [floor, setFloor] = useState(() => s.graph.nodes.find(n => n.kind === 'office')?.floor ?? 1);
  const [worker, setWorker] = useState(0);
  const plan = s.last_plan;
  const b = s.building;
  const mode: RouteMode = b.route_mode === 'lean' ? 'lean' : 'fastest';
  useEffect(() => { if (floor > b.floors) setFloor(1); if (worker && !plan?.routes.some(r => r.worker === worker)) setWorker(0); }, [b.floors, floor, plan, worker]);
  const calculate = async (changes = {}) => {
    const trigger = document.activeElement as HTMLElement | null;
    const result = await mutate('/plan', changes);
    requestAnimationFrame(() => {
      if (trigger?.isConnected && document.activeElement === document.body) trigger.focus({ preventScroll: true });
    });
    return result;
  };
  const routes = plan && !plan.outdated ? plan.routes.filter(r => !worker || r.worker === worker) : [];
  const labels = new Map(s.graph.nodes.map(n => [n.id, n.label]));
  const points = new Map(s.graph.nodes.map(n => [n.id, n]));
  const offices = s.graph.nodes.filter(n => n.kind === 'office'), depots = s.graph.nodes.filter(n => n.kind === 'depot');
  const endName = depots.length ? '분리수거장' : '관리자실';
  const where = (list: typeof offices, name: string) => list.length === 1 ? `${name}(${list[0].floor}F ${list[0].label})` : `${name} ${list.length}곳 중 가까운 곳`;
  const fresh = plan && !plan.outdated && plan.routes.length > 0 && plan.mode ? plan : null;
  const idle = fresh ? b.available_staff - fresh.routes.length : 0;
  const capMinutes = b.max_work_minutes ?? 0, over = fresh?.routes.filter(r => r.over_limit).length ?? 0;
  const conditions = [`계단 ↑${b.stairs_up_seconds ?? 20}초 ↓${b.stairs_down_seconds ?? 14}초/층`, `엘리베이터 대기 ${b.elevator_wait_seconds ?? 40}초 + ${b.elevator_floor_seconds ?? 4}초/층`,
    b.use_cart ? '카트 사용(엘리베이터만)' : '카트 없음', b.cart_capacity ? `한 번에 칸 ${b.cart_capacity}개 분량` : '옮길 양 제한 없음',
    `출발 ${offices.length ? where(offices, '관리자실') : '관리자실 없음'}`, `끝나는 곳 ${depots.length ? where(depots, '분리수거장') : offices.length ? '관리자실' : '없음'}`, capMinutes ? `한 사람 ${capMinutes}분까지` : '작업 시간 상한 없음'];
  return <section className="route-section panel" id="route-planner" tabIndex={-1} aria-label="수거 경로 계획">
    <div className="route-section-header"><SectionTitle eyebrow="상태 확인 다음, 수거 계획" title="관리자별 수거 동선" description={`${offices.length > 1 ? '가까운 관리자실' : '관리자실'}에서 출발해 수거를 마치고 ${endName}에서 비우는 데까지의 경로입니다.`} /><button className="button primary" disabled={busy} onClick={() => calculate()}>{busy ? <Loader2 aria-hidden="true" size={16} className="spin" /> : <RouteIcon aria-hidden="true" size={17} />}{busy ? '처리 중…' : plan ? '경로 다시 계산' : '수거 경로 계산'}</button></div>
    <span className="visually-hidden" role="status">{busy ? "수거 계획을 처리하고 있습니다." : plan?.outdated ? "상태가 바뀌었습니다. 경로를 다시 계산해 주세요." : plan?.blocked_reason === "capacity" ? "운반 용량이 부족해 경로를 배정하지 못했습니다." : plan?.unassigned.length ? "수거 가능한 관리자가 없습니다." : plan ? `계산 완료. 수거 대상 ${plan.target_ids.length}개, 배정 관리자 ${plan.routes.length}명.` : ""}</span>
    <fieldset className="route-mode"><legend className="visually-hidden">동선 계산 방식</legend>{routeModes.map(m => {
      const result = plan && !plan.outdated ? plan.comparison?.[m.id] : undefined;
      return <label key={m.id} className={mode === m.id ? "route-choice active" : "route-choice"}><input className="visually-hidden" type="radio" name={modeGroup} value={m.id} checked={mode === m.id} disabled={busy} onChange={() => calculate({ route_mode: m.id })} /><span className="route-mode-title"><i />{m.title}</span><small>{result && result.workers ? <><b>{duration(result.makespan_seconds)}</b>에 끝남 · 관리자 <b>{result.workers}명</b> · 작업 합계 {duration(result.total_seconds ?? 0)}</> : m.desc}</small></label>;
    })}</fieldset>
    <div className="route-controls"><div className="orange-control"><span className="orange-dot" /><Toggle label="주황색 쓰레기통도 포함" checked={b.include_orange} onChange={include_orange => calculate({ include_orange })} disabled={busy} /><span className="control-hint">{b.include_orange ? '빨강 + 주황' : '빨강만 수거'}</span></div><div className="staff-control"><Users aria-hidden="true" size={16} /><span>수거 가능 인원</span><div className="stepper"><button aria-label="수거 인원 줄이기" disabled={busy || b.available_staff === 0} onClick={() => calculate({ available_staff: b.available_staff - 1 })}><Minus aria-hidden="true" size={13} /></button><strong>{b.available_staff}<small>명</small></strong><button aria-label="수거 인원 늘리기" disabled={busy || b.available_staff >= b.total_staff} onClick={() => calculate({ available_staff: b.available_staff + 1 })}><Plus aria-hidden="true" size={13} /></button></div><span className="control-hint">/ 전체 {b.total_staff}명</span></div></div>
    <details className="route-condition-details"><summary>이동·운반 조건 확인<ChevronDown aria-hidden="true" size={16} /></summary><div className="route-conditions">{conditions.map(c => <i key={c}>{c}</i>)}<button className="text-link" onClick={() => navigate('settings')}>설정에서 바꾸기<ArrowUpRight aria-hidden="true" size={13} /></button></div></details>
    {plan && !plan.outdated && !!plan.issues?.length && <div className="plan-warning plan-issues"><AlertCircle aria-hidden="true" size={16} /><div><strong>경로를 계산하려면 고쳐야 할 곳이 있습니다</strong><ul>{plan.issues.map(issue => <li key={issue}>{issue}</li>)}</ul><button className="text-link" onClick={() => navigate(plan.blocked_reason === 'capacity' ? 'settings' : 'map')}>{plan.blocked_reason === 'capacity' ? '운반 용량 설정 확인' : '건물·배치도에서 고치기'}<ArrowUpRight aria-hidden="true" size={13} /></button></div></div>}
    {plan?.outdated && <div className="plan-warning"><AlertCircle aria-hidden="true" size={16} />조건이 바뀌어 이전 경로를 숨겼습니다. 최신 정보로 경로를 다시 계산해 주세요.</div>}
    {plan && !plan.outdated && !plan.blocked_reason && <div className="route-summary"><span><MapPin aria-hidden="true" size={15} />수거 대상 <b>{plan.target_ids.length + plan.unreachable.length}개</b></span><span><Users aria-hidden="true" size={15} />배정 관리자 <b>{plan.routes.length}명</b></span><span><Clock3 aria-hidden="true" size={15} />끝나는 시간 <b>{duration(plan.makespan_seconds)}</b></span><span><Clock3 aria-hidden="true" size={15} />작업 합계 <b>{duration(plan.total_seconds ?? plan.routes.reduce((t, r) => t + r.duration_seconds, 0))}</b></span><span><Footprints aria-hidden="true" size={15} />걷는 거리 <b>{plan.total_distance_m}m</b></span><small>{dateTime(plan.created_at, true)} 계산</small></div>}
    {fresh && <div className="plan-note"><Clock3 aria-hidden="true" size={16} /><span>{fresh.mode === 'lean' ? `한 사람 작업 시간${capMinutes ? ` ${capMinutes}분` : ''} 안에서 가장 적은 인원으로, 그중 마지막 관리자가 가장 빨리 끝나는 배정입니다.` : `마지막 관리자가 ${endName}에서 비우기를 마치는 시각이 가장 빠른 배정입니다. 같은 시각이면 작업 시간 합계가 짧은 쪽을 골랐습니다.`}{idle > 0 ? ` ${idle}명은 대기합니다.` : ''}</span></div>}
    {over > 0 && <div className="plan-warning"><AlertCircle aria-hidden="true" size={16} />한 사람 작업 시간 상한({capMinutes}분)을 넘는 관리자가 {over}명 있습니다. 수거 가능 인원을 늘리거나 설정에서 상한을 조정하세요.</div>}
    <div className="route-body"><div className="route-map-wrap"><div className="map-toolbar"><span><Layers3 aria-hidden="true" size={15} />층별 수거 경로</span><FloorTabs value={floor} floors={b.floors} onChange={setFloor} /></div><MapView workspace={s} floor={floor} routes={routes} onBinClick={openBin} /><div className="map-legend"><span><i className="legend-office"><Home aria-hidden="true" size={10} /></i>관리자실</span>{depots.length > 0 && <span><i className="legend-depot"><Recycle aria-hidden="true" size={10} /></i>분리수거장</span>}<span><ColorDot color={statusColor.critical} />수거 필요</span><span><ColorDot color={statusColor.warning} />주의</span><span><ColorDot color={statusColor.normal} />정상</span>{plan && !plan.outdated && plan.routes.length ? <><span><i className="legend-route" />가는 방향(오른쪽 통행)</span><span><i className="legend-route back" />마지막 수거 후 {depots.length ? '분리수거장으로' : '관리자실로'}</span></> : null}<small>도면 속 숫자 = 방문 순서</small></div>{plan && !plan.outdated && plan.routes.length ? <div className="worker-filter"><button aria-pressed={worker === 0} className={worker === 0 ? 'active' : ''} onClick={() => setWorker(0)}>전체 경로</button>{plan.routes.map(r => <button key={r.worker} aria-pressed={worker === r.worker} className={worker === r.worker ? 'active' : ''} onClick={() => setWorker(r.worker)}><ColorDot color={r.color} />관리자 {r.worker}</button>)}</div> : <div className="map-footnote">복도·계단을 따라 이동합니다. 건물·배치도에서 위치와 통로를 편집할 수 있습니다.</div>}</div>
      <div className="route-list"><div className="route-list-title"><strong>관리자별 수거 순서</strong><span>{plan && !plan.outdated ? plan.routes.length : 0}개 경로</span></div>
        {!plan ? <Empty title="수거 동선을 준비해 볼까요?" icon={<RouteIcon aria-hidden="true" size={29} />}>주황색 포함 여부와 관리자 수를 정한 뒤<br />수거 경로를 계산해 주세요.</Empty> : plan.outdated ? <Empty title="새로운 상태로 다시 계산해 주세요" icon={<RefreshCw aria-hidden="true" size={28} />} action={<button className="button secondary" disabled={busy} onClick={() => calculate()}>경로 다시 계산</button>}>최신 센서 값과 운영 조건을 반영하면<br />관리자별 수거 순서가 표시됩니다.</Empty> : plan.blocked_reason === 'capacity' ? <Empty title="운반 용량이 부족합니다" action={<button className="button secondary" onClick={() => navigate('settings')}>운반 용량 설정 확인</button>}>한 위치의 수거량이 운반 용량을 넘습니다.<br />용량과 수거 상태를 확인한 뒤 다시 계산해 주세요.</Empty> : plan.unassigned.length ? <Empty title="수거 가능한 관리자가 없습니다" icon={<Users aria-hidden="true" size={27} />} action={<button className="button secondary" disabled={busy} onClick={() => calculate({ available_staff: 1 })}>관리자 1명으로 계산</button>}>수거 가능 인원을 1명 이상으로 설정하면<br />{plan.unassigned.length}개의 쓰레기통을 배정합니다.</Empty> : !plan.routes.length ? <Empty title={plan.unreachable.length ? '연결된 수거 경로가 없습니다' : '지금은 수거할 곳이 없어요'} icon={<Check aria-hidden="true" size={28} />}>{plan.unreachable.length ? '위의 안내대로 건물·배치도에서 통로 연결을 고친 뒤 다시 계산해 주세요.' : '수거 대상이 생기면 이곳에서 경로를 안내합니다.'}</Empty> : plan.routes.map(r => <div key={r.worker} className={`worker-route ${worker && worker !== r.worker ? 'dimmed' : ''}`}>
          <div className="worker-route-header"><span className="worker-avatar" style={{ background: `${r.color}15`, color: r.color }}><Users aria-hidden="true" size={17} /></span><div><strong>관리자 {r.worker}</strong><small>{r.bin_ids.length}개 수거 · {r.distance_m}m{(r.drops ?? 1) > 1 ? ` · 비우기 ${r.drops}번` : ''}</small></div><span className={`route-time ${r.over_limit ? 'over' : ''}`} title={r.over_limit ? '작업 시간 상한 초과' : undefined}>{duration(r.duration_seconds)}</span></div>
          {(() => {
            const sequence = r.sequence ?? [...r.bin_ids, 'OFFICE'];
            const start = r.start ? points.get(r.start) : offices[0];
            // plans made before offices and drop-off points were map points end at 'DEPOT' or 'OFFICE'
            const place = (id: string) => points.get(id) ?? { label: id === 'DEPOT' ? '분리수거장' : '관리자실', kind: id === 'DEPOT' ? 'depot' : 'office', floor: undefined };
            const moves = floorMoves(r, sequence, labels);
            const moveRows = (leg: number) => moves[leg].map((m, i) => <button key={`move-${leg}-${i}`} className="route-stop route-move" title={`${m.to}층 경로 보기`} onClick={() => setFloor(m.to)}><span>{m.to > m.from ? <ArrowUp aria-hidden="true" size={12} /> : <ArrowDown aria-hidden="true" size={12} />}</span><p>{m.from}F → {m.to}F <small>{m.via} 이용</small></p></button>);
            return <div className="route-stops"><div className="route-stop endpoint"><span><Home aria-hidden="true" size={12} /></span><p>{start?.label ?? '관리자실'} <small>{start ? `${start.floor}F · ` : ''}출발</small></p></div>{moveRows(0)}{sequence.map((id, k) => {
              const last = k === sequence.length - 1;
              if (!s.bins.some(x => x.id === id)) { const end = place(id); return <Fragment key={`end-${k}`}><div className={`route-stop endpoint ${end.kind === 'depot' ? 'drop' : ''}`}><span>{end.kind === 'depot' ? <Recycle aria-hidden="true" size={12} /> : <Home aria-hidden="true" size={12} />}</span><p>{end.label} <small>{end.floor ? `${end.floor}F · ` : ''}{last ? '비우고 마침' : '비우고 계속'}</small></p></div>{!last && moveRows(k + 1)}</Fragment>; }
              const bin = s.bins.find(x => x.id === id)!, order = r.bin_ids.indexOf(id) + 1;
              return <Fragment key={id}><div className="route-stop"><span style={{ color: r.color, borderColor: `${r.color}55` }}>{order}</span><button className="stop-main" onClick={() => openBin(id)}><strong>{id}</strong><small>{bin.floor}F · {bin.name}{plan.empty?.[id] ? ` · ${fillText(plan.empty[id])}` : ''}</small></button><i className={`stop-fill ${bin.status}`}>{bin.fill}%</i></div>{moveRows(k + 1)}</Fragment>;
            })}</div>;
          })()}
        </div>)}
        {plan && !plan.outdated && !!plan.unreachable.length && <div className="unreachable"><AlertCircle aria-hidden="true" size={15} /><div><strong>경로 연결 확인 필요</strong><p>{plan.unreachable.join(', ')}</p><small>{b.use_cart ? '카트를 쓰면 계단으로 갈 수 없어 엘리베이터가 없는 층은 배정에서 제외됩니다.' : '배정에서 제외된 쓰레기통입니다.'}</small></div></div>}
      </div></div><div className="route-footer"><Sparkles aria-hidden="true" size={14} /><span>계단은 오르내림을 따로, 엘리베이터는 기다리는 시간을 한 번 넣어 계산한 이동 시간으로 동선을 찾습니다. 예상 시간에는 이동, 수거, 비우는 시간이 포함됩니다.</span></div>
  </section>;
}

export function Dashboard(props: PageProps) {
  const { s, busy, mutate, navigate, openBin } = props;
  const [floor, setFloor] = useState(0);
  const [filter, setFilter] = useState('all');
  const [order, setOrder] = useState('priority');
  const [scenarios, setScenarios] = useState(false);
  const scenarioRef = useRef<HTMLDivElement>(null);
  const scenarioButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!scenarios) return;
    const outside = (e: MouseEvent) => { if (!scenarioRef.current?.contains(e.target as Node)) setScenarios(false); };
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') { setScenarios(false); scenarioButton.current?.focus(); } };
    document.addEventListener('click', outside); document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('click', outside); document.removeEventListener('keydown', escape); };
  }, [scenarios]);
  useEffect(() => { if (floor > s.building.floors) setFloor(0); }, [floor, s.building.floors]);
  const count = (status: Status) => s.bins.filter(b => b.status === status).length;
  const critical = count('critical'), warning = count('warning'), offline = count('offline');
  const targets = critical + (s.building.include_orange ? warning : 0);
  const destination = s.graph.nodes.some(n => n.kind === 'depot') ? '분리수거장' : '관리자실';
  const real = s.bins.find(b => b.device_type === 'real');
  const rank: Record<Status, number> = { critical: 0, warning: 1, offline: 2, pending: 3, normal: 4 };
  const bins = s.bins.filter(b => (!floor || b.floor === floor) && (filter === 'all' || b.status === filter))
    .sort((a, b) => (order === 'priority' ? rank[a.status] - rank[b.status] : 0) || a.id.localeCompare(b.id));
  const currentDate = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric', weekday: 'long' }).format(new Date());
  const sensorState = !real || real.reading_source === 'unconnected' ? '연결 대기'
    : real.reading_source === 'simulated' ? '시뮬레이션' : real.status === 'offline' ? '수신 지연'
    : real.partial_reading ? '일부 칸 수신' : '정상 수신';
  function jumpToPlan() {
    const el = document.getElementById('route-planner');
    el?.focus({ preventScroll: true });
    el?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
  }
  const stats = [
    { id: 'all', label: '전체 쓰레기통', value: s.bins.length, detail: `${s.building.floors}개 층에 배치`, icon: Trash2 },
    { id: 'critical', label: '수거 필요', value: critical, detail: `칸별 ${s.building.critical_threshold}% 이상`, icon: AlertCircle },
    { id: 'warning', label: '주의', value: warning, detail: s.building.include_orange ? '수거 대상에 포함' : '포함 여부 선택 가능', icon: Clock3 },
    { id: 'offline', label: '수신 대기', value: offline, detail: offline ? '연결 상태 확인 필요' : '수신 대기 없음', icon: Radio },
  ];
  return <>
    <div className="page-heading dashboard-heading">
      <div><div className="eyebrow"><Building2 aria-hidden="true" size={14} />{s.building.name}</div><h1>오늘의 수거 현황</h1><p>쓰레기통 상태를 확인하고, 필요한 곳부터 수거하세요.</p></div>
      <span className="today-label"><Clock3 aria-hidden="true" size={14} />{currentDate}</span>
    </div>
    <div className="operations-overview">
      <section className="collection-brief" aria-labelledby="collection-brief-title">
        <span className="brief-label"><span className="brief-indicator" />오늘의 수거 계획</span>
        <h2 id="collection-brief-title">{targets ? <><strong>{targets}</strong>곳을 수거할<br />{' '}차례입니다.</> : <>지금은 수거할 곳이<br />{' '}없어요.</>}</h2>
        <p>{s.building.include_orange ? '수거 필요와 주의 상태를 함께 수거합니다.' : '수거 필요 상태를 먼저 수거합니다.'}{offline > 0 && ` 수신 대기 ${offline}개는 별도로 확인해 주세요.`}</p>
        <div className="collection-journey" aria-label="수거 흐름"><span><Home aria-hidden="true" size={16} />관리자실</span><ArrowRight size={14} aria-hidden="true" /><span><Trash2 aria-hidden="true" size={16} />수거 대상</span><ArrowRight size={14} aria-hidden="true" /><span><Recycle aria-hidden="true" size={16} />{destination}</span></div>
        <div className="brief-actions"><button className="button brief-primary" onClick={jumpToPlan}>수거 계획 세우기<ArrowDown aria-hidden="true" size={16} /></button><button className="brief-staff" onClick={() => navigate('team')}><Users aria-hidden="true" size={16} /><span>수거 가능 <b>{s.building.available_staff}</b> / {s.building.total_staff}명</span><ArrowUpRight aria-hidden="true" size={15} /></button></div>
      </section>
      <section className="live-sensor panel" aria-label="실물 센서 수신 현황">
        <div className="live-sensor-heading"><span><Radio aria-hidden="true" size={16} />실물 센서</span><span className={`sensor-state ${real?.reading_source === 'actual' && real.status !== 'offline' ? 'connected' : ''}`}><i />{sensorState}</span></div>
        {real ? <>
          <div className="live-sensor-reading"><div><button className="sensor-bin-link" onClick={() => openBin(real.id)}>{real.id}<ArrowUpRight aria-hidden="true" size={15} /></button><span>{real.floor}층 {real.name}</span><div className="sensor-value">{real.fill === null ? <strong className="no-reading">첫 측정을 기다려요</strong> : <><strong>{Math.round(real.fill)}</strong><span>%</span><Badge status={real.status} /></>}</div><small>{sourceText[real.reading_source]}{real.fill !== null ? ' · 가장 찬 칸 기준' : ''}</small></div><BinArt fill={real.fill} status={real.status} large /></div>
          <CompartmentRow values={real.compartments} building={s.building} /><SensorNotice bin={real} />
          <div className="live-sensor-footer"><span>{real.measured_at ? `최근 측정 ${dateTime(real.measured_at, true)}` : '연결 후 측정값이 자동으로 표시됩니다'}</span><button className="text-link" onClick={() => navigate('device')}>장치 연동<ArrowRight aria-hidden="true" size={14} /></button></div>
        </> : <Empty title="실물 장치를 확인해 주세요">건물 배치에 등록된 실물 쓰레기통이 없습니다.</Empty>}
      </section>
    </div>
    <div className="metric-grid overview-stats" role="group" aria-label="상태별 쓰레기통 보기">{stats.map(item => <button key={item.id} className={`metric-card ${item.id}`} aria-pressed={filter === item.id && floor === 0} onClick={() => { setFilter(item.id); setFloor(0); }}>
      <div className="metric-card-top"><span>{item.label}</span><item.icon aria-hidden="true" size={18} /></div><div className="metric-number">{item.value}<small>개</small></div><div className="metric-caption">{item.detail}<ArrowRight aria-hidden="true" size={13} /></div>
    </button>)}</div>
    <div className="demo-strip"><span className="demo-strip-icon"><Sparkles aria-hidden="true" size={17} /></span><div><strong>대회 시연</strong><span>실물 {s.bins.filter(b => b.device_type === 'real').length}대 + 더미 {s.bins.filter(b => b.device_type === 'demo').length}개 · 더미 상태를 바꾸어 경로를 비교해 보세요.</span></div>
      <div ref={scenarioRef} className="scenario-wrap"><button ref={scenarioButton} className="scenario-button" aria-expanded={scenarios} aria-controls="demo-scenarios" onClick={() => setScenarios(!scenarios)} disabled={busy}>시나리오 선택<ChevronDown aria-hidden="true" size={14} /></button>
        {scenarios && <div className="scenario-menu" id="demo-scenarios" role="group" aria-label="시연 시나리오">{[{ id: 'mixed', title: '일반적인 하루', desc: '정상 · 주의 · 수거 필요가 섞인 상태' }, { id: 'rush', title: '점심시간 이후', desc: '여러 층에 수거 대상이 많은 상태' }, { id: 'calm', title: '수거를 마친 건물', desc: '모든 더미 쓰레기통이 정상인 상태' }].map(item => <button key={item.id} onClick={async () => { setScenarios(false); scenarioButton.current?.focus(); await mutate('/demo/scenario', { scenario: item.id }, 'POST', `${item.title} 시나리오를 적용했습니다.`); }}><strong>{item.title}</strong><small>{item.desc}</small></button>)}</div>}
      </div>
    </div>
    <section className="bin-section" aria-label="쓰레기통 현황">
      <div className="bin-section-heading"><SectionTitle title="쓰레기통 현황" action={<span className="count-pill">{bins.length} / {s.bins.length}</span>} /><MiniLink onClick={() => navigate('map')}>배치도에서 보기</MiniLink></div>
      <div className="bin-toolbar"><FloorTabs value={floor} floors={s.building.floors} onChange={setFloor} all /><div className="bin-toolbar-right"><select aria-label="쓰레기통 상태 필터" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">전체 상태</option><option value="critical">수거 필요</option><option value="warning">주의</option><option value="normal">정상</option><option value="offline">수신 대기</option><option value="pending">수거 확인 중</option></select><select aria-label="쓰레기통 정렬" value={order} onChange={e => setOrder(e.target.value)}><option value="priority">수거 필요 우선</option><option value="number">번호순</option></select></div></div>
      <div className="bin-grid">{bins.map(bin => <button key={bin.id} className={`bin-card ${bin.status} ${bin.device_type === 'real' ? 'real' : ''}`} onClick={() => openBin(bin.id)} aria-label={`${bin.id}, ${bin.floor}층 ${bin.name}, ${statusText[bin.status]}, ${bin.fill === null ? '측정값 없음' : `최대 적재율 ${Math.round(bin.fill)}%`}, 상세 보기`}>
        <div className="bin-card-top"><span className="bin-id">{bin.id}{bin.device_type === 'real' && <Radio aria-hidden="true" size={12} />}</span><Badge status={bin.status} /></div>
        <div className="bin-card-body"><BinArt fill={bin.fill} status={bin.status} /><div><span className="bin-fill-label">{topCompartment(bin.compartments) ? `최대 · ${compartmentName[topCompartment(bin.compartments)!]}` : '현재 적재율'}</span><strong>{bin.fill === null ? '—' : Math.round(bin.fill)}{bin.fill !== null && <small>%</small>}</strong></div></div>
        <CompartmentRow values={bin.compartments} building={s.building} /><SensorNotice bin={bin} />
        <div className="bin-card-bottom"><span><MapPin aria-hidden="true" size={12} />{bin.floor}F <i />{bin.name}</span><span className="bin-source">{bin.device_type === 'real' ? bin.reading_source === 'simulated' ? '시뮬레이션' : '실물' : '더미'}</span></div>
      </button>)}</div>
      {bins.length === 0 && <Empty title="선택한 조건의 쓰레기통이 없습니다" action={<button className="button secondary" onClick={() => { setFloor(0); setFilter('all'); }}>전체 쓰레기통 보기</button>}>다른 층이나 상태를 선택해 보세요.</Empty>}
      <div className="bin-legend"><span><i className="normal" />정상 · {s.building.warning_threshold}% 미만</span><span><i className="warning" />주의 · {s.building.warning_threshold}~{s.building.critical_threshold}% 미만</span><span><i className="critical" />수거 필요 · {s.building.critical_threshold}% 이상</span><span className="card-hint">카드를 선택하면 상세 정보와 수거 완료를 확인할 수 있습니다.</span></div>
    </section>
    <RoutePanel {...props} />
  </>;
}
