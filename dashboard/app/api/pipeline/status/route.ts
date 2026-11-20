import { API_BASE, hasLocalOperator } from '../operator';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const res = await fetch(`${API_BASE}/pipeline/status`, { cache: 'no-store' });
  const data = await res.json();
  return Response.json(data, {
    status: res.status,
    headers: {
      'Cache-Control': 'no-store',
      'X-Pipeline-Local-Operator': String(hasLocalOperator(req)),
    },
  });
}
