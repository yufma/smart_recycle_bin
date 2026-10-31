import { Fragment, useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowDown, ArrowRight, ArrowUp, ArrowUpRight, Building2, Check, ChevronDown, Clock3, Footprints, Home, Layers3, Loader2, MapPin, Minus, Plus, Radio, Recycle, RefreshCw, Route as RouteIcon, Sparkles, Trash2, Users } from 'lucide-react';
import type { PageProps } from './App';
import type { Route, RouteMode, Status } from './types';
import { compartmentName, dateTime, duration, fillText, sourceText, statusColor, topCompartment } from './types';
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
  const [floor, setFloor] = useState(() => s.graph.nodes.find(n => n.kind === 'office')?.floor ?? 1);
  const [worker, setWorker] = useState(0);
  const plan = s.last_plan;
  const b = s.building;
  const mode: RouteMode = b.route_mode === 'lean' ? 'lean' : 'fastest';
  useEffect(() => { if (floor > b.floors) setFloor(1); if (worker && !plan?.routes.some(r => r.worker === worker)) setWorker(0); }, [b.floors, floor, plan, worker]);
  const calculate = (changes = {}) => mutate('/plan', changes);
  const routes = plan?.routes.filter(r => !worker || r.worker === worker) || [];
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
  return <section className="route-section panel" id="route-planner">
    <div className="route-section-header"><SectionTitle eyebrow="SMART COLLECTION" title="필요한 곳을 잇는 수거 동선" description={`${offices.length > 1 ? '가까운 관리자실' : '관리자실'}에서 출발해 수거를 마치고 ${endName}에서 비우는 데까지의 경로입니다.`} /><button className="button primary" disabled={busy} onClick={() => calculate()}>{busy ? <Loader2 size={16} className="spin" /> : <RouteIcon size={17} />}{plan ? '경로 다시 계산' : '수거 경로 계산'}</button></div>
    <div className="route-mode" role="radiogroup" aria-label="동선 계산 방식">{routeModes.map(m => {
      const result = plan && !plan.outdated ? plan.comparison?.[m.id] : undefined;
      return <button key={m.id} role="radio" aria-checked={mode === m.id} className={mode === m.id ? 'active' : ''} disabled={busy} onClick={() => { if (mode !== m.id) calculate({ route_mode: m.id }); }}><span className="route-mode-title"><i />{m.title}</span><small>{result && result.workers ? <><b>{duration(result.makespan_seconds)}</b>에 끝남 · 관리자 <b>{result.workers}명</b> · 작업 합계 {duration(result.total_seconds ?? 0)}</> : m.desc}</small></button>;
    })}</div>
    <div className="route-controls"><div className="orange-control"><span className="orange-dot" /><Toggle label="주황색 쓰레기통도 포함" checked={b.include_orange} onChange={include_orange => calculate({ include_orange })} disabled={busy} /><span className="control-hint">{b.include_orange ? '빨강 + 주황' : '빨강만 수거'}</span></div><div className="staff-control"><Users size={16} /><span>수거 가능 인원</span><div className="stepper"><button aria-label="수거 인원 줄이기" disabled={busy || b.available_staff === 0} onClick={() => calculate({ available_staff: b.available_staff - 1 })}><Minus size={13} /></button><strong>{b.available_staff}<small>명</small></strong><button aria-label="수거 인원 늘리기" disabled={busy || b.available_staff >= b.total_staff} onClick={() => calculate({ available_staff: b.available_staff + 1 })}><Plus size={13} /></button></div><span className="control-hint">/ 전체 {b.total_staff}명</span></div></div>
    <div className="route-conditions"><span>이동 조건</span>{conditions.map(c => <i key={c}>{c}</i>)}<button className="text-link" onClick={() => navigate('settings')}>설정에서 바꾸기<ArrowUpRight size={13} /></button></div>
    {plan && !plan.outdated && !!plan.issues?.length && <div className="plan-warning plan-issues"><AlertCircle size={16} /><div><strong>경로를 계산하려면 고쳐야 할 곳이 있습니다</strong><ul>{plan.issues.map(issue => <li key={issue}>{issue}</li>)}</ul><button className="text-link" onClick={() => navigate(plan.blocked_reason === 'capacity' ? 'settings' : 'map')}>{plan.blocked_reason === 'capacity' ? '운반 용량 설정 확인' : '건물·배치도에서 고치기'}<ArrowUpRight size={13} /></button></div></div>}
    {plan?.outdated && <div className="plan-warning"><AlertCircle size={16} />쓰레기통 상태, 배치 또는 이동 조건이 바뀌었습니다. 최신 정보로 경로를 다시 계산해 주세요.</div>}
    {plan && !plan.blocked_reason && <div className="route-summary"><span><MapPin size={15} />수거 대상 <b>{plan.target_ids.length + plan.unreachable.length}개</b></span><span><Users size={15} />배정 관리자 <b>{plan.routes.length}명</b></span><span><Clock3 size={15} />끝나는 시간 <b>{duration(plan.makespan_seconds)}</b></span><span><Clock3 size={15} />작업 합계 <b>{duration(plan.total_seconds ?? plan.routes.reduce((t, r) => t + r.duration_seconds, 0))}</b></span><span><Footprints size={15} />걷는 거리 <b>{plan.total_distance_m}m</b></span><small>{dateTime(plan.created_at, true)} 계산</small></div>}
    {fresh && <div className="plan-note"><Clock3 size={16} /><span>{fresh.mode === 'lean' ? `한 사람 작업 시간${capMinutes ? ` ${capMinutes}분` : ''} 안에서 가장 적은 인원으로, 그중 마지막 관리자가 가장 빨리 끝나는 배정입니다.` : `마지막 관리자가 ${endName}에서 비우기를 마치는 시각이 가장 빠른 배정입니다. 같은 시각이면 작업 시간 합계가 짧은 쪽을 골랐습니다.`}{idle > 0 ? ` ${idle}명은 대기합니다.` : ''}</span></div>}
    {over > 0 && <div className="plan-warning"><AlertCircle size={16} />한 사람 작업 시간 상한({capMinutes}분)을 넘는 관리자가 {over}명 있습니다. 수거 가능 인원을 늘리거나 설정에서 상한을 조정하세요.</div>}
    <div className="route-body"><div className="route-map-wrap"><div className="map-toolbar"><span><Layers3 size={15} />층별 수거 경로</span><FloorTabs value={floor} floors={b.floors} onChange={setFloor} /></div><MapView workspace={s} floor={floor} routes={routes} onBinClick={openBin} /><div className="map-legend"><span><i className="legend-office"><Home size={10} /></i>관리자실</span>{depots.length > 0 && <span><i className="legend-depot"><Recycle size={10} /></i>분리수거장</span>}<span><ColorDot color={statusColor.critical} />수거 필요</span><span><ColorDot color={statusColor.warning} />주의</span><span><ColorDot color={statusColor.normal} />정상</span>{plan?.routes.length ? <><span><i className="legend-route" />가는 방향(오른쪽 통행)</span><span><i className="legend-route back" />마지막 수거 후 {depots.length ? '분리수거장으로' : '관리자실로'}</span></> : null}<small>도면 속 숫자 = 방문 순서</small></div>{plan?.routes.length ? <div className="worker-filter"><button className={worker === 0 ? 'active' : ''} onClick={() => setWorker(0)}>전체 경로</button>{plan.routes.map(r => <button key={r.worker} className={worker === r.worker ? 'active' : ''} onClick={() => setWorker(r.worker)}><ColorDot color={r.color} />관리자 {r.worker}</button>)}</div> : <div className="map-footnote">복도·계단을 따라 이동합니다. 건물·배치도에서 위치와 통로를 편집할 수 있습니다.</div>}</div>
      <div className="route-list"><div className="route-list-title"><strong>관리자별 수거 순서</strong><span>{plan?.routes.length || 0} ROUTES</span></div>
        {!plan ? <Empty title="수거 동선을 준비해 볼까요?" icon={<RouteIcon size={29} />}>주황색 포함 여부와 관리자 수를 정한 뒤<br />수거 경로를 계산해 주세요.</Empty> : plan.blocked_reason === 'capacity' ? <Empty title="운반 용량이 부족합니다">한 위치의 수거량이 운반 용량을 넘습니다.<br />용량과 수거 상태를 확인한 뒤 다시 계산해 주세요.</Empty> : plan.unassigned.length ? <Empty title="수거 가능한 관리자가 없습니다" icon={<Users size={27} />}>수거 가능 인원을 1명 이상으로 설정하면<br />{plan.unassigned.length}개의 쓰레기통을 배정합니다.</Empty> : !plan.routes.length ? <Empty title={plan.unreachable.length ? '연결된 수거 경로가 없습니다' : '지금은 수거할 곳이 없어요'} icon={<Check size={28} />}>{plan.unreachable.length ? '위의 안내대로 건물·배치도에서 통로 연결을 고친 뒤 다시 계산해 주세요.' : '수거 대상이 생기면 이곳에서 경로를 안내합니다.'}</Empty> : plan.routes.map(r => <div key={r.worker} className={`worker-route ${worker && worker !== r.worker ? 'dimmed' : ''}`}>
          <div className="worker-route-header"><span className="worker-avatar" style={{ background: `${r.color}15`, color: r.color }}><Users size={17} /></span><div><strong>관리자 {r.worker}</strong><small>{r.bin_ids.length}개 수거 · {r.distance_m}m{(r.drops ?? 1) > 1 ? ` · 비우기 ${r.drops}번` : ''}</small></div><span className={`route-time ${r.over_limit ? 'over' : ''}`} title={r.over_limit ? '작업 시간 상한 초과' : undefined}>{duration(r.duration_seconds)}</span></div>
          {(() => {
            const sequence = r.sequence ?? [...r.bin_ids, 'OFFICE'];
            const start = r.start ? points.get(r.start) : offices[0];
            // plans made before offices and drop-off points were map points end at 'DEPOT' or 'OFFICE'
            const place = (id: string) => points.get(id) ?? { label: id === 'DEPOT' ? '분리수거장' : '관리자실', kind: id === 'DEPOT' ? 'depot' : 'office', floor: undefined };
            const moves = floorMoves(r, sequence, labels);
            const moveRows = (leg: number) => moves[leg].map((m, i) => <button key={`move-${leg}-${i}`} className="route-stop route-move" title={`${m.to}층 경로 보기`} onClick={() => setFloor(m.to)}><span>{m.to > m.from ? <ArrowUp size={12} /> : <ArrowDown size={12} />}</span><p>{m.from}F → {m.to}F <small>{m.via} 이용</small></p></button>);
            return <div className="route-stops"><div className="route-stop endpoint"><span><Home size={12} /></span><p>{start?.label ?? '관리자실'} <small>{start ? `${start.floor}F · ` : ''}출발</small></p></div>{moveRows(0)}{sequence.map((id, k) => {
              const last = k === sequence.length - 1;
              if (!s.bins.some(x => x.id === id)) { const end = place(id); return <Fragment key={`end-${k}`}><div className={`route-stop endpoint ${end.kind === 'depot' ? 'drop' : ''}`}><span>{end.kind === 'depot' ? <Recycle size={12} /> : <Home size={12} />}</span><p>{end.label} <small>{end.floor ? `${end.floor}F · ` : ''}{last ? '비우고 마침' : '비우고 계속'}</small></p></div>{!last && moveRows(k + 1)}</Fragment>; }
              const bin = s.bins.find(x => x.id === id)!, order = r.bin_ids.indexOf(id) + 1;
              return <Fragment key={id}><div className="route-stop"><span style={{ color: r.color, borderColor: `${r.color}55` }}>{order}</span><button className="stop-main" onClick={() => openBin(id)}><strong>{id}</strong><small>{bin.floor}F · {bin.name}{plan.empty?.[id] ? ` · ${fillText(plan.empty[id])}` : ''}</small></button><i className={`stop-fill ${bin.status}`}>{bin.fill}%</i></div>{moveRows(k + 1)}</Fragment>;
            })}</div>;
          })()}
        </div>)}
        {!!plan?.unreachable.length && <div className="unreachable"><AlertCircle size={15} /><div><strong>경로 연결 확인 필요</strong><p>{plan.unreachable.join(', ')}</p><small>{b.use_cart ? '카트를 쓰면 계단으로 갈 수 없어 엘리베이터가 없는 층은 배정에서 제외됩니다.' : '배정에서 제외된 쓰레기통입니다.'}</small></div></div>}
      </div></div><div className="route-footer"><Sparkles size={14} /><span>계단은 오르내림을 따로, 엘리베이터는 기다리는 시간을 한 번 넣어 계산한 이동 시간으로 동선을 찾습니다. 예상 시간에는 이동, 수거, 비우는 시간이 포함됩니다.</span></div>
  </section>;
}

export function Dashboard(props: PageProps) {
  const { s, busy, mutate, navigate, openBin } = props;
  const [floor, setFloor] = useState(0); const [filter, setFilter] = useState('all'); const [scenarios, setScenarios] = useState(false);
  const scenarioRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!scenarios) return; const listener = (e: MouseEvent) => { if (!scenarioRef.current?.contains(e.target as Node)) setScenarios(false); }; document.addEventListener('click', listener); return () => document.removeEventListener('click', listener); }, [scenarios]);
  const critical = s.bins.filter(b => b.status === 'critical').length, warning = s.bins.filter(b => b.status === 'warning').length;
  const real = s.bins.find(b => b.device_type === 'real');
  const bins = s.bins.filter(b => (!floor || b.floor === floor) && (filter === 'all' || b.status === filter));
  const currentDate = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }).format(new Date());
  async function makePlan() {
    const result = await mutate('/plan');
    if (result) { navigate('team'); setTimeout(() => document.getElementById('route-planner')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60); }
  }
  return <><div className="page-heading"><div><div className="eyebrow">OVERVIEW <span>/</span> {s.building.name}</div><h1>한눈에 보는 수거 현황<span className="heading-dot">.</span></h1><p>공간의 상태를 살피고, 필요한 곳부터 수거하세요.</p></div><div className="heading-actions"><span className="today-label"><Clock3 size={14} />{currentDate}</span><button className="button primary" disabled={busy} onClick={makePlan}><RouteIcon size={17} />수거 경로 계산<ArrowUpRight size={16} /></button></div></div>
    <div className="metric-grid"><div className="metric-card"><div className="metric-card-top"><span>전체 쓰레기통</span><span className="metric-symbol neutral"><Trash2 size={18} /></span></div><div className="metric-number">{s.bins.length}<small>개</small></div><div className="metric-caption"><Building2 size={13} />{s.building.floors}개 층에 배치되어 있어요</div></div>
    <div className="metric-card critical"><div className="metric-card-top"><span>수거 필요</span><span className="metric-symbol critical"><AlertCircle size={18} /></span></div><div className="metric-number">{critical}<small>개</small><span className="metric-tag">{s.building.critical_threshold}% 이상</span></div><div className="metric-caption"><i className="tiny-dot" />우선 수거가 필요한 쓰레기통</div></div>
    <div className="metric-card warning"><div className="metric-card-top"><span>주의 상태</span><span className="metric-symbol warning"><Clock3 size={18} /></span></div><div className="metric-number">{warning}<small>개</small><span className="metric-tag">{s.building.warning_threshold}% 이상</span></div><div className="metric-caption"><i className="tiny-dot" />수거 동선에 포함할 수 있어요</div></div>
    <div className="metric-card staff"><div className="metric-card-top"><span>수거 가능한 관리자</span><span className="metric-symbol green"><Users size={18} /></span></div><div className="metric-number">{s.building.available_staff}<small>/ {s.building.total_staff}명</small><div className="mini-avatars">{[1, 2, 3].slice(0, Math.min(s.building.available_staff, 3)).map(i => <span key={i}>{String(i).padStart(2, '0')}</span>)}</div></div><button className="metric-link" onClick={() => navigate('team')}>관리 인원 설정<ArrowRight size={13} /></button></div></div>
    <div className="demo-strip"><span className="demo-strip-icon"><Sparkles size={17} /></span><div><strong>시연 워크스페이스</strong><span>실물 장치 1대와 더미 쓰레기통 {s.bins.filter(b => b.device_type === 'demo').length}개로 수거 흐름을 확인하세요.</span></div><div ref={scenarioRef} className="scenario-wrap"><button className="scenario-button" onClick={() => setScenarios(!scenarios)} disabled={busy}>시연 시나리오<ChevronDown size={14} /></button>{scenarios && <div className="scenario-menu">{[{ id: 'mixed', title: '일반적인 하루', desc: '정상 · 주의 · 수거 필요가 섞인 상태' }, { id: 'rush', title: '점심시간 이후', desc: '여러 층에 수거 대상이 많은 상태' }, { id: 'calm', title: '수거를 마친 건물', desc: '모든 더미 쓰레기통이 정상인 상태' }].map(item => <button key={item.id} onClick={async () => { setScenarios(false); await mutate('/demo/scenario', { scenario: item.id }, 'POST', `${item.title} 시나리오를 적용했습니다.`); }}><strong>{item.title}</strong><small>{item.desc}</small></button>)}</div>}</div></div>
    <section className="bin-section"><div className="bin-section-heading"><SectionTitle title="쓰레기통 현황" action={<span className="count-pill">{s.bins.length}</span>} /><MiniLink onClick={() => navigate('map')}>배치도에서 보기</MiniLink></div><div className="bin-toolbar"><FloorTabs value={floor} floors={s.building.floors} onChange={setFloor} all /><div className="bin-toolbar-right">{real && <button className={`device-live ${real.reading_source === 'actual' && real.status !== 'offline' ? 'connected' : ''}`} onClick={() => navigate('device')}><Radio size={13} />{real.reading_source === 'actual' ? real.status === 'offline' ? '실물 수신 지연' : real.partial_reading ? '일부 칸 수신 대기' : '실물 센서 연결됨' : real.reading_source === 'simulated' ? '실물 위치 시뮬레이션' : '실물 센서 연결 대기'}</button>}<select aria-label="쓰레기통 상태 필터" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">전체 상태</option><option value="critical">수거 필요</option><option value="warning">주의</option><option value="normal">정상</option><option value="offline">수신 대기</option><option value="pending">수거 확인 중</option></select></div></div>
    <div className="bin-grid">{bins.map(bin => <button key={bin.id} className={`bin-card ${bin.status} ${bin.device_type === 'real' ? 'real' : ''}`} onClick={() => openBin(bin.id)}><div className="bin-card-top"><span className="bin-id">{bin.id}{bin.device_type === 'real' && <Radio size={12} />}</span><Badge status={bin.status} /></div><div className="bin-card-body"><BinArt fill={bin.fill} status={bin.status} /><div><span className="bin-fill-label">{topCompartment(bin.compartments) ? `최대 · ${compartmentName[topCompartment(bin.compartments)!]}` : '현재 적재율'}</span><strong>{bin.fill === null ? '—' : Math.round(bin.fill)}<small>%</small></strong></div></div><CompartmentRow values={bin.compartments} building={s.building} /><SensorNotice bin={bin} /><div className="bin-card-bottom"><span><MapPin size={12} />{bin.floor}F <i />{bin.name}</span><span className={`bin-source ${bin.device_type === 'real' ? 'real-source' : ''}`}>{bin.device_type === 'real' ? bin.reading_source === 'simulated' ? '시뮬레이션' : '실물' : '더미'}</span></div></button>)}</div>{bins.length === 0 && <Empty title="조건에 맞는 쓰레기통이 없습니다">층 또는 상태 필터를 변경해 주세요.</Empty>}<div className="bin-legend"><span><i className="normal" />정상 · {s.building.warning_threshold}% 미만</span><span><i className="warning" />주의 · {s.building.warning_threshold}~{s.building.critical_threshold}% 미만</span><span><i className="critical" />수거 필요 · {s.building.critical_threshold}% 이상</span><span className="card-hint">카드를 눌러 상세 정보와 수거 완료를 확인하세요<ArrowUpRight size={12} /></span></div></section>
  </>;
}
