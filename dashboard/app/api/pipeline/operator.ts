import 'server-only';

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

function localOperatorToken(req: Request) {
  const localOrigin = process.env.PIPELINE_LOCAL_ORIGIN;
  if (!localOrigin) return undefined;

  const { origin, host } = new URL(localOrigin);
  if (req.headers.get('host') !== host) return undefined;
  if (req.method === 'POST' && req.headers.get('origin') !== origin) return undefined;

  return process.env.PIPELINE_OPERATOR_TOKEN;
}

export function hasLocalOperator(req: Request) {
  return Boolean(localOperatorToken(req));
}

export async function proxyPipelineRun(req: Request, path: string) {
  const authorization = req.headers.get('authorization');
  const token = authorization === null ? localOperatorToken(req) : undefined;
  const headers = new Headers({ Accept: 'text/event-stream' });
  if (authorization !== null) headers.set('Authorization', authorization);
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const upstream = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    cache: 'no-store',
    redirect: 'error',
    signal: req.signal,
    headers,
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('content-type') ?? 'application/json',
      'Cache-Control': 'no-cache, no-transform',
      'X-Accel-Buffering': 'no',
    },
  });
}
