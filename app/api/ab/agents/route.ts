// BFF — GET /api/ab/agents et POST /api/ab/agents.
// Persistance des brouillons dans Prisma. Aucune intégration externe
// (OpenWebUI) : on stocke le snapshot complet dans config_snapshot (table
// ab_agent_versions) et un owui_model_id qui sert d'identifiant/slug interne.

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/db';
import { inspectInput, DEFAULT_GUARD_CONFIG, BLOCK_MESSAGE_AGENT_CONFIG } from '@/lib/prompt-guard';
import { recordGuardEvent } from '@/lib/guard-audit';

function buildAgentSlug(name: string, uniqueSuffix: string): string {
  const slug = name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
  return `mirai-${slug}-${uniqueSuffix.slice(0, 6)}`;
}

type AgentDraftPayload = {
  name?: string;
  description?: string;
  category?: string;
  visibility?: 'private' | 'community' | 'ministry';
  communityPath?: string | null;
  systemPrompt?: string;
  greeting?: string;
  examples?: string[];
  modelId?: string;
  temperature?: number;
  status?: 'draft' | 'published' | 'submitted';
};

async function requireSession() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return { ok: false as const, error: NextResponse.json({ error: 'unauthorized' }, { status: 401 }) };
  }
  return { ok: true as const, session };
}

export async function GET() {
  const r = await requireSession();
  if (!r.ok) return r.error;

  const agents = await prisma.agent.findMany({
    where: { creatorId: r.session.user.id },
    orderBy: { updatedAt: 'desc' },
    take: 100,
  });

  return NextResponse.json({
    agents: agents.map((a) => ({
      id: a.id,
      owuiModelId: a.owuiModelId,
      visibility: a.visibility,
      status: a.status,
      category: a.category,
      tags: a.tags,
      version: a.version,
      createdAt: a.createdAt,
      updatedAt: a.updatedAt,
    })),
  });
}

export async function POST(req: Request) {
  const r = await requireSession();
  if (!r.ok) return r.error;

  const body = (await req.json().catch(() => ({}))) as AgentDraftPayload;

  if (!body.name || body.name.trim().length === 0) {
    return NextResponse.json({ error: 'name_required' }, { status: 400 });
  }
  if (!body.systemPrompt || body.systemPrompt.trim().length === 0) {
    return NextResponse.json({ error: 'system_prompt_required' }, { status: 400 });
  }

  // Garde anti-supply-chain : un créateur ne doit pas pouvoir publier un agent
  // dont le system prompt (ou les contenus annexes) embarque un keylogger ou une
  // consigne d'injection. On inspecte tout le contenu fourni par le créateur.
  const creatorContent = [
    body.systemPrompt,
    body.description ?? '',
    body.greeting ?? '',
    ...(body.examples ?? []),
  ].join('\n\n');
  const inGuard = inspectInput(creatorContent, 'system', { anomaly: DEFAULT_GUARD_CONFIG.anomaly });
  if (inGuard.signals.some((s) => s.complied)) {
    await recordGuardEvent({
      route: 'agents.create',
      stage: 'input',
      userId: r.session.user.id,
      role: 'system',
      signals: inGuard.signals,
    });
  }
  if (inGuard.blocked) {
    return NextResponse.json(
      { error: 'blocked_input', message: BLOCK_MESSAGE_AGENT_CONFIG },
      { status: 422 },
    );
  }

  const owuiModelId =
    body.name
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 60) || 'agent';

  // Validation des enums : on n'accepte que des valeurs connues, defaut sur le
  // niveau le plus restrictif. NOTE (a valider) : le droit de publier en
  // community/ministry devra etre conditionne a un mecanisme de groupes
  // (non implemente en mode standalone).
  const VISIBILITIES = ['private', 'community', 'ministry'] as const;
  const STATUSES = ['draft', 'published', 'submitted'] as const;
  const visibility = VISIBILITIES.includes(body.visibility as never)
    ? (body.visibility as (typeof VISIBILITIES)[number])
    : 'private';
  const status = STATUSES.includes(body.status as never)
    ? (body.status as (typeof STATUSES)[number])
    : 'draft';

  // Snapshot complet de la config du wizard — servira à recréer l'état
  // exact du brouillon à l'édition et, plus tard, à appeler OpenWebUI.
  const configSnapshot = {
    name: body.name,
    description: body.description ?? '',
    category: body.category ?? '',
    visibility,
    communityPath: body.communityPath ?? null,
    systemPrompt: body.systemPrompt,
    greeting: body.greeting ?? '',
    examples: body.examples ?? [],
    modelId: body.modelId ?? null,
    temperature: body.temperature ?? 0.7,
  };

  // Generer l'id/slug interne de l'agent
  const uniqueSuffix = Date.now().toString(36);
  const finalOwuiModelId = buildAgentSlug(body.name!, uniqueSuffix);

  try {
    const agent = await prisma.agent.create({
      data: {
        owuiModelId: finalOwuiModelId,
        creatorId: r.session.user.id,
        visibility,
        status,
        category: body.category ? [body.category] : [],
        tags: [],
        version: 1,
        versions: {
          create: {
            version: 1,
            configSnapshot,
            changelog: 'Creation initiale via le wizard',
          },
        },
      },
    });

    return NextResponse.json({
      id: agent.id,
      status,
      name: body.name,
      owuiModelId: finalOwuiModelId,
    });
  } catch (err) {
    console.error('persistence_failure', err);
    return NextResponse.json({ error: 'persistence_failure' }, { status: 500 });
  }
}
