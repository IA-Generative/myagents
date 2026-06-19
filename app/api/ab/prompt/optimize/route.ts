// BFF — "Optimiser mon prompt" (§3.1).
// Même squelette que /assist : appel direct à Scaleway Generative APIs.

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { scwChatCompletions, ScwLlmUnavailableError } from '@/lib/scw-llm-client';
import { rateLimit, LLM_RATE_LIMIT } from '@/lib/rate-limit';
import { inspectInput, inspectOutput, logGuardEvent } from '@/lib/prompt-guard';

const OPTIMIZER_PROMPT = `Tu es un assistant qui réécrit des prompts système pour des
agents IA ministériels. Améliore la clarté, la structure, ajoute des garde-fous si
manquants (ne jamais inventer de sources juridiques, citer les textes, limiter les
réponses au périmètre de l'agent). Retourne UNIQUEMENT le prompt amélioré, sans
préambule ni commentaire.`;

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  if (!rateLimit(`optimize:${session.user?.id ?? 'anon'}`, LLM_RATE_LIMIT)) {
    return NextResponse.json({ error: 'rate_limited' }, { status: 429 });
  }

  const body = (await req.json().catch(() => ({}))) as { prompt?: string };
  if (!body.prompt || body.prompt.trim().length === 0) {
    return NextResponse.json({ error: 'prompt_required' }, { status: 400 });
  }

  // Garde d'entrée : le prompt à optimiser est fourni par l'utilisateur.
  const inGuard = inspectInput(body.prompt, 'user');
  if (inGuard.blocked) {
    logGuardEvent({
      route: 'prompt.optimize',
      stage: 'input',
      userId: session.user?.id,
      role: 'user',
      signals: inGuard.signals,
    });
    return NextResponse.json({ error: 'blocked_input' }, { status: 422 });
  }

  try {
    const completion = await scwChatCompletions({
      messages: [
        { role: 'system', content: OPTIMIZER_PROMPT },
        { role: 'user', content: body.prompt },
      ],
      temperature: 0.4,
    });
    const optimized = completion.choices?.[0]?.message?.content?.trim() ?? body.prompt;
    const outGuard = inspectOutput(optimized);
    if (outGuard.blocked) {
      logGuardEvent({
        route: 'prompt.optimize',
        stage: 'output',
        userId: session.user?.id,
        signals: outGuard.signals,
      });
      return NextResponse.json({ error: 'blocked_output' }, { status: 422 });
    }
    return NextResponse.json({ prompt: optimized });
  } catch (err) {
    if (err instanceof ScwLlmUnavailableError) {
      return NextResponse.json(
        { error: 'llm_not_configured', detail: err.message },
        { status: 501 },
      );
    }
    console.error('optimize upstream_failure', err);
    return NextResponse.json({ error: 'upstream_failure' }, { status: 502 });
  }
}
