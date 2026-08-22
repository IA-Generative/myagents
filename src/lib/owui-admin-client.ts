// Client admin OpenWebUI — cree/met a jour/supprime des modeles-wrappers
// via l'API REST d'OpenWebUI (POST /api/v1/models/create, etc.)
// Utilise OWUI_ADMIN_API_KEY (cle API d'un admin OpenWebUI) et
// OWUI_BASE_URL (URL interne du service K8s/Docker).

import { env } from './env';

export class OwuiAdminUnavailableError extends Error {
  constructor() {
    super('OpenWebUI admin API non configure (OWUI_ADMIN_API_KEY manquant).');
    this.name = 'OwuiAdminUnavailableError';
  }
}

type CreateModelPayload = {
  id: string;
  name: string;
  description: string;
  systemPrompt: string;
  baseModelId: string;
  temperature: number;
  greeting?: string;
  examples?: string[];
};

type OwuiModelResponse = {
  id: string;
  name: string;
  user_id: string;
  base_model_id: string;
  is_active: boolean;
};

function getHeaders(): HeadersInit {
  const e = env();
  if (!e.OWUI_ADMIN_API_KEY) throw new OwuiAdminUnavailableError();
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${e.OWUI_ADMIN_API_KEY}`,
  };
}

function baseUrl(): string {
  return env().OWUI_BASE_URL.replace(/\/$/, '');
}

// Partage de l'agent dans OpenWebUI. A partir de la version 0.11, le partage ne passe
// plus par `access_control` mais par une liste `access_grants`, et deux details comptent :
//
//  - une liste ABSENTE ou nulle fait echouer la mise a jour avec un 500 dont le corps ne
//    dit rien (la trace n'existe que dans le journal du socle) ;
//  - une liste VIDE veut dire « visible du seul proprietaire », c'est-a-dire du compte
//    qui porte la cle d'administration. L'agent apparait alors dans l'interface
//    d'administration et nulle part ailleurs, sans qu'aucun message ne le signale.
//
// `user/*` = tout compte connecte. Surtout pas `anyone/*`, qui vaut « sans
// authentification » et que le socle retire d'office sur cette route.
const PARTAGE_TOUT_COMPTE_CONNECTE = [
  { principal_type: 'user', principal_id: '*', permission: 'read' },
];

export async function createOwuiModel(p: CreateModelPayload): Promise<OwuiModelResponse> {
  const body = {
    id: p.id,
    name: `${p.name} (Mes Agents MirAI)`,
    meta: {
      description: p.description || `Agent cree via Mes Agents MirAI`,
      profile_image_url: '/static/favicon.png',
      suggestion_prompts: (p.examples ?? []).map((content) => ({ content })),
      tags: [{ name: 'Mes Agents MirAI' }],
      capabilities: { vision: false, usage: false, citations: true },
    },
    params: {
      system: p.systemPrompt,
      temperature: p.temperature,
    },
    base_model_id: p.baseModelId,
    access_control: null,
    access_grants: PARTAGE_TOUT_COMPTE_CONNECTE,
    is_active: true,
  };

  const res = await fetch(`${baseUrl()}/api/v1/models/create`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10000),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`OpenWebUI createModel ${res.status}: ${detail.slice(0, 300)}`);
  }

  return (await res.json()) as OwuiModelResponse;
}

export async function updateOwuiModel(p: CreateModelPayload): Promise<OwuiModelResponse> {
  // OpenWebUI v0.8.12 : POST /api/v1/models/model/update avec l'id dans le body
  const body = {
    id: p.id,
    name: p.name,
    meta: {
      description: p.description,
      profile_image_url: '/static/favicon.png',
      suggestion_prompts: (p.examples ?? []).map((content) => ({ content })),
      capabilities: { vision: false, usage: false, citations: true },
    },
    params: {
      system: p.systemPrompt,
      temperature: p.temperature,
    },
    base_model_id: p.baseModelId,
    access_control: null,
    access_grants: PARTAGE_TOUT_COMPTE_CONNECTE,
    is_active: true,
  };

  // L'identifiant part AUSSI en parametre de requete : les socles recents l'y attendent,
  // les anciens le lisent dans le corps. Sans lui, la mise a jour echoue et le repli
  // tente une creation, qui repond 401 « already registered » — un code
  // d'authentification pour un conflit de nom, de quoi chercher au mauvais endroit.
  const res = await fetch(`${baseUrl()}/api/v1/models/model/update?id=${encodeURIComponent(p.id)}`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10000),
  });

  if (!res.ok) {
    // Fallback : delete + create
    try { await deleteOwuiModel(p.id); } catch { /* ignore */ }
    return createOwuiModel(p);
  }

  return (await res.json()) as OwuiModelResponse;
}

export async function deleteOwuiModel(id: string): Promise<void> {
  // Essayer plusieurs patterns car l'API varie selon les versions
  for (const [method, path] of [
    ['POST', `/api/v1/models/model/delete`],
    ['DELETE', `/api/v1/models/${encodeURIComponent(id)}`],
  ] as const) {
    const res = await fetch(`${baseUrl()}${path}`, {
      method,
      headers: getHeaders(),
      body: method === 'POST' ? JSON.stringify({ id }) : undefined,
      signal: AbortSignal.timeout(10000),
    });
    if (res.ok || res.status === 404) return;
  }
}

export function buildOwuiModelId(name: string, uniqueSuffix: string): string {
  const slug = name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40);
  return `mirai-${slug}-${uniqueSuffix.slice(0, 6)}`;
}
