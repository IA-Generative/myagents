// GET /api/ab/models — liste des modèles LLM réellement disponibles sur
// l'instance Scaleway, fusionnée avec les fiches curated (cf. src/lib/models).
//
// - La clé SCW reste côté serveur (jamais exposée au client).
// - Cache en mémoire (TTL 1h) pour ne pas interroger Scaleway à chaque chargement
//   du wizard. ?refresh=1 force un rafraîchissement (bouton « Actualiser »).
// - Repli : si Scaleway est indisponible, on renvoie le dernier cache (même
//   périmé) ou, à défaut, le catalogue statique — l'UI reste toujours utilisable.

import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { scwListModels, ScwLlmUnavailableError } from '@/lib/scw-llm-client';
import { owuiServedModelIds } from '@/lib/owui-admin-client';
import { AVAILABLE_MODELS, mergeLiveModels, type ModelProfile } from '@/lib/models';

const TTL_MS = 60 * 60 * 1000; // 1 heure

let cache: { models: ModelProfile[]; fetchedAt: number } | null = null;

export async function GET(req: Request) {
  const session = await getServerSession(authOptions);
  if (!session) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const refresh = new URL(req.url).searchParams.get('refresh') === '1';
  const now = Date.now();

  if (!refresh && cache && now - cache.fetchedAt < TTL_MS) {
    return NextResponse.json({
      models: cache.models,
      fetchedAt: cache.fetchedAt,
      source: 'cache',
    });
  }

  try {
    const live = await scwListModels();
    // On ne propose QUE des modèles utilisables de bout en bout : servis par le
    // hub ET exposés par Mon assistant. Le socle n'expose qu'une partie du hub
    // (cf. OPENAI_API_CONFIGS) — un modèle choisi hors de cette intersection
    // répond au banc d'essai puis donne « Model not found » une fois l'agent
    // publié. Panne du 2026-09-23. Si le socle est injoignable, on n'ampute
    // rien : mieux vaut une liste trop large qu'un sélecteur vide.
    const duSocle = await owuiServedModelIds();
    const utilisables = duSocle ? live.filter((m) => duSocle.has(m.id)) : live;
    const models = mergeLiveModels(utilisables.length > 0 ? utilisables : live);
    cache = { models, fetchedAt: now };
    return NextResponse.json({ models, fetchedAt: now, source: 'live' });
  } catch (err) {
    console.error('models fetch failed', err);
    // Repli gracieux : dernier cache connu, sinon catalogue statique.
    if (cache) {
      return NextResponse.json({
        models: cache.models,
        fetchedAt: cache.fetchedAt,
        source: 'stale',
      });
    }
    return NextResponse.json({
      models: AVAILABLE_MODELS,
      fetchedAt: now,
      source: err instanceof ScwLlmUnavailableError ? 'fallback' : 'fallback-error',
    });
  }
}
