import type { NextRequest } from 'next/server';
import { proxyPipelineRun } from '../operator';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  const rebuild = req.nextUrl.searchParams.get('rebuild') === 'true';
  return proxyPipelineRun(req, `/pipeline/run-all?rebuild=${rebuild}`);
}
