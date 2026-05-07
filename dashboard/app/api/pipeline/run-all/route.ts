import type { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export async function GET(_req: NextRequest) {
  const upstream = await fetch(`${API_BASE}/pipeline/run-all`, {
    cache: 'no-store',
    headers: { Accept: 'text/event-stream' },
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'X-Accel-Buffering': 'no',
    },
  });
}
