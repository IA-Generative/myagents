// BFF — GET /api/ab/agents et POST /api/ab/agents.
// Persistance des brouillons dans Prisma. L'intégration OpenWebUI (création
// du modèle-wrapper via POST /api/models/create) n'est pas encore en place ;
// on stocke simplement le snapshot complet dans config_snapshot (table
// ab_agent_versions) et un owui_model_id de placeholder.

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/db';
import {
  createOwuiModel,
  buildOwuiModelId,
  OwuiAdminUnavailableError,
} from '@/lib/owui-admin-client';
import { inspectInput, BLOCK_MESSAGE_AGENT_CONFIG } from '@/lib/prompt-guard';
import { recordGuardEvent } from '@/lib/guard-audit';

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
  const inGuard = inspectInput(creatorContent, 'system');
  if (inGuard.blocked) {
    await recordGuardEvent({
      route: 'agents.create',
      stage: 'input',
      userId: r.session.user.id,
      role: 'system',
      signals: inGuard.signals,
    });
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
  // community/ministry devra etre conditionne a l'appartenance au groupe
  // Keycloak correspondant — non implemente ici.
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

  // Generer l'id du modele OpenWebUI
  const uniqueSuffix = Date.now().toString(36);
  const finalOwuiModelId = buildOwuiModelId(body.name!, uniqueSuffix);

  // Si publication (pas draft), creer le modele dans OpenWebUI
  let owuiCreated = false;
  if (status !== 'draft') {
    try {
      await createOwuiModel({
        id: finalOwuiModelId,
        name: body.name!,
        description: configSnapshot.description,
        systemPrompt: configSnapshot.systemPrompt,
        baseModelId: configSnapshot.modelId ?? 'gpt-oss-120b',
        temperature: configSnapshot.temperature,
        greeting: configSnapshot.greeting,
        examples: configSnapshot.examples,
      });
      owuiCreated = true;
    } catch (err) {
      if (err instanceof OwuiAdminUnavailableError) {
        // Non bloquant : on cree quand meme en base, juste pas dans OWUI
        console.warn('OpenWebUI admin non configure, agent cree en base seulement');
      } else {
        console.error('Erreur creation modele OpenWebUI:', err);
      }
    }
  }

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
      owuiCreated,
    });
  } catch (err) {
    console.error('persistence_failure', err);
    return NextResponse.json({ error: 'persistence_failure' }, { status: 500 });
  }
}
