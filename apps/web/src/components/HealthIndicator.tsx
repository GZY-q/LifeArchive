import { useEffect, useState } from 'react';

import { checkHealth } from '../api/health';

type HealthStatus = 'loading' | 'healthy' | 'unavailable';

const statusText: Record<HealthStatus, string> = {
  loading: '正在检查连接',
  healthy: '服务已连接',
  unavailable: '暂时无法连接服务',
};

export function HealthIndicator() {
  const [status, setStatus] = useState<HealthStatus>('loading');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 8_000);

    void checkHealth(controller.signal)
      .then(() => {
        if (active) setStatus('healthy');
      })
      .catch(() => {
        if (active) setStatus('unavailable');
      })
      .finally(() => window.clearTimeout(timeout));

    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  function retry() {
    setStatus('loading');
    setAttempt((current) => current + 1);
  }

  return (
    <section className="connection" aria-label="服务连接">
      <p className={`connection-status ${status}`} role="status">
        <span className="status-dot" aria-hidden="true" />
        {statusText[status]}
      </p>
      <button
        className="connection-retry"
        type="button"
        onClick={retry}
        disabled={status === 'loading'}
      >
        {status === 'unavailable' ? '重新检查连接' : '检查连接'}
      </button>
    </section>
  );
}
