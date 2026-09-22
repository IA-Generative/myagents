// BFF — GET / PUT / DELETE /api/ab/agents/:id
// GET  : retourne l'agent + son dernier config snapshot (pour hydrater le wizard edit)
// PUT  : met a jour l'agent (nouvelle version dans ab_agent_versions) et, s'il
//        est publie, son modele dans Mon assistant (OpenWebUI)
// DELETE : soft delete (status = archived)

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/db';
import { inspectInput, DEFAULT_GUARD_CONFIG, BLOCK_MESSAGE_AGENT_CONFIG } from '@/lib/prompt-guard';
import { recordGuardEvent } from '@/lib/guard-audit';
import { updateOwuiModel, OwuiAdminUnavailableError } from '@/lib/owui-admin-client';

// Statuts pour lesquels la creation a pousse le modele dans OpenWebUI
// (POST /api/ab/agents : tout sauf « draft »). Un agent archive n'est pas
// republie par une modification.
const STATUTS_PUBLIES = ['published', 'submitted', 'validated'];

async function requireOwner(agentId: string) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return { ok: false as const, res: NextResponse.json({ error: 'unauthorized' }, { status: 401 }) };
  }
  const agent = await prisma.agent.findUnique({
    where: { id: agentId },
    include: { versions: { orderBy: { version: 'desc' }, take: 1 } },
  });
  if (!agent) {
    return { ok: false as const, res: NextResponse.json({ error: 'not_found' }, { status: 404 }) };
  }
  if (agent.creatorId !== session.user.id) {
    return { ok: false as const, res: NextResponse.json({ error: 'forbidden' }, { status: 403 }) };
  }
  return { ok: true as const, agent, session };
}

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const r = await requireOwner(id);
  if (!r.ok) return r.res;

  const snapshot = r.agent.versions[0]?.configSnapshot ?? {};

  return NextResponse.json({
    id: r.agent.id,
    owuiModelId: r.agent.owuiModelId,
    status: r.agent.status,
    visibility: r.agent.visibility,
    category: r.agent.category,
    version: r.agent.version,
    createdAt: r.agent.createdAt,
    updatedAt: r.agent.updatedAt,
    config: snapshot,
  });
}

export async function PUT(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const r = await requireOwner(id);
  if (!r.ok) return r.res;

  const body = await req.json().catch(() => ({}));

  // Garde anti-supply-chain à l'édition : même contrôle qu'à la création.
  const creatorContent = [
    body.systemPrompt ?? '',
    body.description ?? '',
    body.greeting ?? '',
    ...(Array.isArray(body.examples) ? body.examples : []),
  ].join('\n\n');
  const inGuard = inspectInput(creatorContent, 'system', { anomaly: DEFAULT_GUARD_CONFIG.anomaly });
  if (inGuard.signals.some((s) => s.complied)) {
    await recordGuardEvent({
      route: 'agents.update',
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

  const newVersion = r.agent.version + 1;
  const visibility = body.visibility ?? r.agent.visibility;
  const status = body.status ?? r.agent.status;

  const configSnapshot = {
    name: body.name ?? '',
    description: body.description ?? '',
    category: body.category ?? '',
    visibility,
    communityPath: body.communityPath ?? null,
    systemPrompt: body.systemPrompt ?? '',
    greeting: body.greeting ?? '',
    examples: body.examples ?? [],
    modelId: body.modelId ?? null,
    temperature: body.temperature ?? 0.7,
  };

  try {
    await prisma.$transaction([
      prisma.agent.update({
        where: { id },
        data: {
          visibility,
          status,
          category: body.category ? [body.category] : r.agent.category,
          version: newVersion,
        },
      }),
      prisma.agentVersion.create({
        data: {
          agentId: id,
          version: newVersion,
          configSnapshot,
          changelog: body.changelog ?? 'Modification via le wizard',
        },
      }),
    ]);
  } catch (err) {
    console.error('update_failed', err);
    return NextResponse.json({ error: 'update_failed' }, { status: 500 });
  }

  // Agent deja publie : sans cet appel, Mon assistant gardait l'ancienne
  // version indefiniment. Meme charge utile qu'a la creation, meme identifiant
  // de modele (celui enregistre en base). Non bloquant, comme a la creation :
  // la nouvelle version est deja en base, on signale seulement l'echec.
  let owuiUpdated: boolean | null = null;
  if (STATUTS_PUBLIES.includes(status)) {
    try {
      await updateOwuiModel({
        id: r.agent.owuiModelId,
        name: configSnapshot.name,
        description: configSnapshot.description,
        systemPrompt: configSnapshot.systemPrompt,
        baseModelId: configSnapshot.modelId ?? 'gpt-oss-120b',
        temperature: configSnapshot.temperature,
        greeting: configSnapshot.greeting,
        examples: configSnapshot.examples,
      });
      owuiUpdated = true;
    } catch (err) {
      owuiUpdated = false;
      if (err instanceof OwuiAdminUnavailableError) {
        console.warn('OpenWebUI admin non configure, agent mis a jour en base seulement');
      } else {
        console.error('Erreur mise a jour modele OpenWebUI:', err);
      }
    }
  }

  return NextResponse.json({ id, version: newVersion, status, owuiUpdated });
}

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const r = await requireOwner(id);
  if (!r.ok) return r.res;

  await prisma.agent.update({
    where: { id },
    data: { status: 'archived' },
  });

  return NextResponse.json({ id, status: 'archived' });
}
