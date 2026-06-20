// BFF — Validation des « Instructions système » par le module anti-jailbreak.
// Appelé par le bouton obligatoire du wizard (étape Comportement). Ne fait PAS
// d'appel LLM : inspection heuristique déterministe via inspectInput('system').
// Tout blocage est tracé dans la file d'audit (ab_guard_events).

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { rateLimit, LLM_RATE_LIMIT } from '@/lib/rate-limit';
import { inspectInput, BLOCK_MESSAGE_AGENT_CONFIG } from '@/lib/prompt-guard';
import { recordGuardEvent } from '@/lib/guard-audit';

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  if (!rateLimit(`validate:${session.user.id}`, LLM_RATE_LIMIT)) {
    return NextResponse.json({ error: 'rate_limited' }, { status: 429 });
  }

  const body = (await req.json().catch(() => ({}))) as { prompt?: string };
  if (!body.prompt || body.prompt.trim().length === 0) {
    return NextResponse.json({ error: 'prompt_required' }, { status: 400 });
  }

  const guard = inspectInput(body.prompt, 'system');
  if (guard.blocked) {
    await recordGuardEvent({
      route: 'prompt.validate',
      stage: 'validate',
      userId: session.user.id,
      role: 'system',
      signals: guard.signals,
    });
    return NextResponse.json(
      { error: 'blocked_input', message: BLOCK_MESSAGE_AGENT_CONFIG },
      { status: 422 },
    );
  }

  return NextResponse.json({ ok: true });
}
