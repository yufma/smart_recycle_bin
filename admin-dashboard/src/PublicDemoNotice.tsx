import { useEffect, useState } from 'react';

export default function PublicDemoNotice() {
  const [status, setStatus] = useState(window.inloopDemoStatus ?? '체험 공간을 준비하고 있습니다.');
  useEffect(() => {
    const update = (event: Event) => setStatus((event as CustomEvent<string>).detail);
    window.addEventListener('inloop-demo-status', update);
    return () => window.removeEventListener('inloop-demo-status', update);
  }, []);
  if (!window.inloopPublicDemo) return null;
  return <div className="public-demo-notice"><strong>공개 체험 · 나만의 데이터</strong><span>변경한 내용은 이 브라우저에만 저장되며 다른 방문자와 섞이지 않습니다.</span><small role="status">{status}</small></div>;
}
