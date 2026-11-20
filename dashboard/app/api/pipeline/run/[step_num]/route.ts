import type { NextRequest } from 'next/server';
import { proxyPipelineRun } from '../../operator';

export const dynamic = 'force-dynamic';

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ step_num: string }> },
) {
  const { step_num } = await params;

  if (!/^[1-9]$/.test(step_num)) return Response.json({ detail: "Invalid step" }, { status: 400 });

  return proxyPipelineRun(req, `/pipeline/run/${step_num}`);
}
