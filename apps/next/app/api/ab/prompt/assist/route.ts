// BFF — "Aide-moi à écrire" (§3.1).
// Appelle Scaleway Generative APIs directement (via src/lib/scw-llm-client).
// Modèle : gpt-oss-120b (default, alignement avec DEFAULT_MODELS du socle).

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { scwChatCompletions, ScwLlmUnavailableError } from '@/lib/scw-llm-client';
import { rateLimit, LLM_RATE_LIMIT } from '@/lib/rate-limit';
import {
  inspectInput,
  inspectOutput,
  judgeOutput,
  DEFAULT_GUARD_CONFIG,
  DEFAULT_OUTPUT_POLICY_GOAL,
  BLOCK_MESSAGE_AGENT_CONFIG,
  BLOCK_MESSAGE_OUTPUT,
} from '@/lib/prompt-guard';
import { recordGuardEvent } from '@/lib/guard-audit';

const SYSTEM_META_PROMPT = `Tu es un assistant qui aide un agent du Ministère de l'Intérieur
à rédiger un prompt système pour son propre agent IA. Propose un prompt structuré, clair,
en français, avec des sections : rôle, public, ton, contraintes. Retourne UNIQUEMENT le
prompt système proposé, sans préambule, sans commentaire, sans guillemets.`;

export async function POST(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  if (!rateLimit(`assist:${session.user?.id ?? 'anon'}`, LLM_RATE_LIMIT)) {
    return NextResponse.json({ error: 'rate_limited' }, { status: 429 });
  }

  const body = (await req.json().catch(() => ({}))) as {
    prompt?: string;
    hints?: Record<string, string>;
  };

  // Garde d'entrée : le prompt + les hints sont fournis par l'utilisateur.
  const inboundContent = `${JSON.stringify(body.hints ?? {})}\n${body.prompt ?? ''}`;
  const inGuard = inspectInput(inboundContent, 'user', { anomaly: DEFAULT_GUARD_CONFIG.anomaly });
  if (inGuard.signals.some((s) => s.complied)) {
    await recordGuardEvent({
      route: 'prompt.assist',
      stage: 'input',
      userId: session.user?.id,
      role: 'user',
      signals: inGuard.signals,
    });
  }
  if (inGuard.blocked) {
    return NextResponse.json(
      { error: 'blocked_input', message: BLOCK_MESSAGE_AGENT_CONFIG },
      { status: 422 },
    );
  }

  const userMessage =
    `Informations fournies par l'utilisateur :\n` +
    JSON.stringify(body.hints ?? {}, null, 2) +
    `\n\nPrompt actuel (vide si nouveau) :\n${body.prompt ?? '(vide)'}\n\n` +
    `Génère ou améliore le prompt système.`;

  try {
    const completion = await scwChatCompletions({
      messages: [
        { role: 'system', content: SYSTEM_META_PROMPT },
        { role: 'user', content: userMessage },
      ],
      temperature: 0.5,
    });
    const generated = completion.choices?.[0]?.message?.content?.trim() ?? '';
    // Garde de sortie : heuristiques (keylogger) + LLM-juge (manipulation /
    // désinformation que la regex ne voit pas). Fail-closed.
    const outHeuristics = inspectOutput(generated);
    const judge = await judgeOutput({ goal: DEFAULT_OUTPUT_POLICY_GOAL, response: generated });
    const outSignals = [
      ...outHeuristics.signals,
      { source: 'judge' as const, complied: judge.complied, reason: judge.reason, severity: 'medium' as const },
    ];
    if (outSignals.some((s) => s.complied)) {
      await recordGuardEvent({
        route: 'prompt.assist',
        stage: 'output',
        userId: session.user?.id,
        signals: outSignals,
      });
      return NextResponse.json(
        { error: 'blocked_output', message: BLOCK_MESSAGE_OUTPUT },
        { status: 422 },
      );
    }
    return NextResponse.json({ prompt: generated });
  } catch (err) {
    if (err instanceof ScwLlmUnavailableError) {
      return NextResponse.json(
        { error: 'llm_not_configured', detail: err.message },
        { status: 501 },
      );
    }
    console.error('assist upstream_failure', err);
    return NextResponse.json({ error: 'upstream_failure' }, { status: 502 });
  }
}
