import { Check, Loader2 } from 'lucide-react';
import type { PageProps } from './App';
import type { Bin, Workspace } from './types';

export function binCollectionDone(s: Workspace, bin: Bin) {
  return !!bin.collection_done || !!(s.last_plan && !s.last_plan.outdated && s.last_plan.completed_bin_ids?.includes(bin.id));
}

type ActionProps = Pick<PageProps, 's' | 'mutate' | 'busy'>;

export function BinCompleteButton({ s, bin, mutate, busy, compact = false, onComplete }: ActionProps & {
  bin: Bin; compact?: boolean; onComplete?: () => void;
}) {
  const done = binCollectionDone(s, bin);
  const pending = bin.awaiting_confirmation;
  const unavailable = bin.fill === null || bin.status === 'offline';
  const empty = bin.fill === 0;
  const plan = s.last_plan && !s.last_plan.outdated ? s.last_plan : null;
  const route = plan?.routes.find(r => r.bin_ids.includes(bin.id));
  const label = pending ? compact ? '확인 대기' : '센서 확인 대기' : done ? compact ? '완료됨' : '수거 완료'
    : unavailable ? compact ? '측정 대기' : '측정값 대기' : empty ? '비어 있음' : compact ? '완료' : '수거 완료';
  return <button type="button" className={`button ${done || pending ? 'collection-done' : 'secondary'} collection-bin-button ${compact ? 'compact' : ''}`}
    disabled={busy || done || pending || unavailable || empty}
    aria-label={`${bin.id} ${pending ? '수거 후 센서 확인 대기' : done ? '수거 완료됨' : unavailable ? '측정값 수신 대기' : empty ? '비어 있음' : '수거 완료 처리'}`}
    onClick={async () => {
      const result = await mutate(`/collect/${bin.id}`, { worker: route?.worker ?? null,
        ...(route && plan?.id ? { plan_id: plan.id } : {}), version: bin.collection_version }, 'POST', `${bin.id} 수거 완료를 기록했습니다.`);
      if (result) onComplete?.();
    }}>
    {busy && !done && !pending ? <Loader2 aria-hidden="true" size={14} className="spin" /> : <Check aria-hidden="true" size={14} />}{label}
  </button>;
}

export function WorkerCompleteButton({ s, worker, mutate, busy }: ActionProps & { worker: number }) {
  const plan = s.last_plan;
  const route = plan?.routes.find(r => r.worker === worker);
  const remaining = route?.bin_ids.filter(id => !plan?.completed_bin_ids?.includes(id)) ?? [];
  const done = !!route && remaining.length === 0;
  const enabled = !!route && !!plan?.id && !plan.outdated && !done;
  const label = plan?.outdated ? '경로를 다시 계산하세요' : done ? '담당 수거 완료됨' : !route ? '배정된 수거 없음' : `담당 수거 완료 (${remaining.length}개)`;
  return <button type="button" className={`button full worker-complete-button ${done ? 'collection-done' : 'primary'}`}
    disabled={busy || !enabled} aria-label={`관리자 ${worker} ${label}`}
    onClick={() => mutate(`/collect/worker/${worker}`, { plan_id: plan!.id }, 'POST', `관리자 ${worker}의 담당 수거 ${remaining.length}개를 완료했습니다.`)}>
    {busy && enabled ? <Loader2 aria-hidden="true" size={15} className="spin" /> : <Check aria-hidden="true" size={15} />}{label}
  </button>;
}
