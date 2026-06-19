// POST /api/ab/agents/:id/chat — chat avec un agent + persistance conversation
// Si conversationId est fourni, on append. Sinon, on cree une nouvelle conversation.

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/db';
import { scwChatCompletions, ScwLlmUnavailableError } from '@/lib/scw-llm-client';
import { rateLimit, LLM_RATE_LIMIT } from '@/lib/rate-limit';
import { env } from '@/lib/env';
import {
  inspectInput,
  inspectOutput,
  judgeOutput,
  hardenSystemPrompt,
  makeCanary,
  DEFAULT_OUTPUT_POLICY_GOAL,
  BLOCK_MESSAGE_USER_INPUT,
  BLOCK_MESSAGE_OUTPUT,
} from '@/lib/prompt-guard';
import { recordGuardEvent } from '@/lib/guard-audit';

export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  if (!rateLimit(`chat:${session.user.id}`, LLM_RATE_LIMIT)) {
    return NextResponse.json({ error: 'rate_limited' }, { status: 429 });
  }

  const agent = await prisma.agent.findUnique({
    where: { id },
    include: { versions: { orderBy: { version: 'desc' }, take: 1 } },
  });
  if (!agent) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  // Contrôle d'accès : seul le proprietaire, ou un agent publie et partage
  // (community/ministry), peut etre instancie. On renvoie 404 (et non 403)
  // pour ne pas confirmer l'existence d'un agent prive a un tiers.
  const isOwner = agent.creatorId === session.user.id;
  const isShared = agent.visibility !== 'private' && agent.status === 'published';
  if (!isOwner && !isShared) {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }

  const snapshot = (agent.versions[0]?.configSnapshot ?? {}) as Record<string, unknown>;
  const systemPrompt = (snapshot.systemPrompt as string) || 'Tu es un assistant.';
  const modelId = (snapshot.modelId as string) || 'gpt-oss-120b';
  const temperature = (snapshot.temperature as number) || 0.7;

  const body = (await req.json().catch(() => ({}))) as {
    messages?: Array<{ role: string; content: string }>;
    conversationId?: string;
  };

  if (!Array.isArray(body.messages) || body.messages.length === 0) {
    return NextResponse.json({ error: 'messages_required' }, { status: 400 });
  }

  // Whitelist stricte des roles : on n'accepte que user/assistant venant du
  // client. Un message role:"system" injecte ici ecraserait le prompt de
  // l'agent — on le filtre. On borne aussi le nombre de messages transmis.
  const clientMessages = body.messages
    .filter(
      (m): m is { role: 'user' | 'assistant'; content: string } =>
        (m?.role === 'user' || m?.role === 'assistant') &&
        typeof m?.content === 'string',
    )
    .slice(-40);

  if (clientMessages.length === 0) {
    return NextResponse.json({ error: 'messages_required' }, { status: 400 });
  }

  // Garde COUCHE 1 — inspection du dernier message utilisateur (injection
  // markers + keylogger brut). Bloque avant tout appel LLM.
  const lastUser = clientMessages[clientMessages.length - 1];
  const inGuard = inspectInput(lastUser.content, 'user');
  if (inGuard.blocked) {
    await recordGuardEvent({
      route: 'chat',
      stage: 'input',
      userId: session.user.id,
      role: 'user',
      signals: inGuard.signals,
    });
    return NextResponse.json(
      { error: 'blocked_input', message: BLOCK_MESSAGE_USER_INPUT },
      { status: 422 },
    );
  }

  // Garde COUCHE 2 — durcissement du system prompt + canari par requête.
  const canary = makeCanary();
  const hardenedSystem = hardenSystemPrompt(systemPrompt, canary);

  // Appel LLM
  let content: string;
  try {
    const completion = await scwChatCompletions({
      model: modelId,
      temperature,
      messages: [
        { role: 'system', content: hardenedSystem },
        ...clientMessages,
      ],
    });
    content = completion.choices?.[0]?.message?.content?.trim() ?? '';
  } catch (err) {
    if (err instanceof ScwLlmUnavailableError) {
      return NextResponse.json({ error: 'llm_not_configured', detail: err.message }, { status: 501 });
    }
    console.error('chat upstream_failure', err);
    return NextResponse.json({ error: 'upstream_failure' }, { status: 502 });
  }

  // Garde COUCHE 3 — inspection de la SORTIE avant de la renvoyer/persister.
  // Heuristiques (keylogger, fuite du canari) + LLM-juge inline (manipulation).
  const outHeuristics = inspectOutput(content, { canary });
  const judge = await judgeOutput({ goal: DEFAULT_OUTPUT_POLICY_GOAL, response: content });
  const outSignals = [
    ...outHeuristics.signals,
    {
      source: 'judge' as const,
      complied: judge.complied,
      reason: judge.reason,
      severity: 'medium' as const,
    },
  ];
  if (outSignals.some((s) => s.complied)) {
    await recordGuardEvent({
      route: 'chat',
      stage: 'output',
      userId: session.user.id,
      role: 'user',
      signals: outSignals,
    });
    // On ne renvoie NI ne persiste la réponse dangereuse (caviardage total).
    return NextResponse.json(
      { error: 'blocked_output', message: BLOCK_MESSAGE_OUTPUT },
      { status: 422 },
    );
  }

  // Persistance de la conversation
  let conversationId = body.conversationId;
  try {
    const lastUserMsg = clientMessages[clientMessages.length - 1];
    if (!conversationId) {
      // Creer une nouvelle conversation
      const conv = await prisma.conversation.create({
        data: {
          agentId: id,
          userId: session.user.id,
          title: lastUserMsg.content.slice(0, 80),
        },
      });
      conversationId = conv.id;

      // Persister tous les messages historiques
      for (const m of clientMessages) {
        await prisma.conversationMessage.create({
          data: {
            conversationId,
            role: m.role,
            content: m.content,
          },
        });
      }
    } else {
      // Append seulement le dernier message user
      await prisma.conversationMessage.create({
        data: {
          conversationId,
          role: lastUserMsg.role,
          content: lastUserMsg.content,
        },
      });
    }

    // Toujours persister la reponse assistant
    await prisma.conversationMessage.create({
      data: {
        conversationId,
        role: 'assistant',
        content,
      },
    });
  } catch {
    // Non-bloquant : si la persistance echoue, on renvoie quand meme la reponse
  }

  return NextResponse.json({
    content,
    conversationId,
    owuiPublicUrl: env().OWUI_PUBLIC_URL || null,
  });
}
