export const dynamic = 'force-dynamic';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';

export async function GET() {
  const res = await fetch(`${API_BASE}/pipeline/status`, { cache: 'no-store' });
  const data = await res.json();
  return Response.json(data, { status: res.status });
}
