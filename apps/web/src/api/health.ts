/** M0 health is API liveness only; it does not claim database readiness. */
export async function checkHealth(signal: AbortSignal): Promise<void> {
  const response = await fetch('/api/v1/health', {
    signal,
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error('Health request failed');
  }

  const body: unknown = await response.json();

  if (
    typeof body !== 'object' ||
    body === null ||
    !('status' in body) ||
    body.status !== 'ok'
  ) {
    throw new Error('Invalid health response');
  }
}
