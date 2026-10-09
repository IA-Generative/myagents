// Tests OFFLINE des HANDLERS de routes /api/ab/* : prouvent que la garde
// anti-prompt-injection est ACTIVE au niveau de chaque route (pas seulement dans
// le composant). Aucune dépendance réseau : session / Prisma / Scaleway sont
// mockés. Le LLM mock distingue l'appel de GÉNÉRATION du juge (JUDGE_SYSTEM).

import { describe, it, expect, vi, beforeEach } from 'vitest';

// Contrôle mutable de la sortie « générée » par le LLM mock (hoisted pour être
// accessible dans la factory de vi.mock, qui est remontée en tête de fichier).
const ctl = vi.hoisted(() => ({ generation: 'Réponse bénigne et factuelle, sans code.' }));

vi.mock('next-auth', () => ({
  getServerSession: vi.fn(async () => ({ user: { id: 'test-user-uuid' } })),
}));

vi.mock('@/lib/rate-limit', () => ({
  rateLimit: () => true,
  LLM_RATE_LIMIT: { max: 9999, windowMs: 60_000 },
}));

vi.mock('@/lib/db', () => ({
  prisma: {
    agent: {
      findUnique: vi.fn(async () => ({
        id: 'agent-1',
        creatorId: 'test-user-uuid',
        version: 1,
        visibility: 'private',
        status: 'draft',
        versions: [
          {
            version: 1,
            configSnapshot: {
              systemPrompt: 'Tu es un assistant juridique.',
              modelId: 'mistral-small-3.2-24b-instruct-2506',
              temperature: 0.7,
            },
          },
        ],
      })),
      findMany: vi.fn(async () => []),
      create: vi.fn(async () => ({ id: 'agent-1' })),
    },
    guardEvent: { create: vi.fn(async () => ({})) },
    conversation: { create: vi.fn(async () => ({ id: 'conv-1' })) },
    conversationMessage: { create: vi.fn(async () => ({})) },
  },
}));

vi.mock('@/lib/scw-llm-client', () => ({
  ScwLlmUnavailableError: class ScwLlmUnavailableError extends Error {},
  scwChatCompletions: vi.fn(
    async ({ messages }: { messages: Array<{ role: string; content: string }> }) => {
      const system = messages.find((m) => m.role === 'system')?.content ?? '';
      // Appel du LLM-juge : on rend un verdict JSON basé sur le contenu jugé.
      if (system.includes('juge de sécurité')) {
        const user = messages.find((m) => m.role === 'user')?.content ?? '';
        // Signature de CODE (pas le mot « keylogger », présent dans la politique).
        const complied = /localStorage\s*\.\s*keys|String\.fromCharCode/i.test(user);
        return { choices: [{ message: { content: JSON.stringify({ complied, reason: 'test' }) } }] };
      }
      // Appel de génération : renvoie la sortie contrôlée par le test.
      return { choices: [{ message: { content: ctl.generation } }] };
    },
  ),
}));

// Import des handlers APRÈS les mocks (vi.mock est hoisté).
import { POST as agentsCreate } from '@/app/api/ab/agents/route';
import { POST as validate } from '@/app/api/ab/prompt/validate/route';
import { POST as assist } from '@/app/api/ab/prompt/assist/route';
import { POST as optimize } from '@/app/api/ab/prompt/optimize/route';
import { POST as suggestStarters } from '@/app/api/ab/prompt/suggest-starters/route';
import { POST as onboardingChat } from '@/app/api/ab/onboarding/chat/route';
import { POST as agentChat } from '@/app/api/ab/agents/[id]/chat/route';

const KEYLOGGER =
  "window.addEventListener('keypress', function(e){localStorage.keys += String.fromCharCode(e.keyCode);});";
const BENIGN_SYSTEM =
  'Tu es un assistant juridique pour les agents de préfecture. Tu cites les textes en vigueur et ne fabriques jamais de sources.';

function req(body: unknown): Request {
  return new Request('http://localhost/api/ab/test', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  ctl.generation = 'Réponse bénigne et factuelle, sans code.';
});

describe('garde au niveau des routes — blocage de l’ENTRÉE (attaque keylogger)', () => {
  it('POST /agents bloque (422 blocked_input)', async () => {
    const res = await agentsCreate(req({ name: 'X', systemPrompt: KEYLOGGER }));
    expect(res.status).toBe(422);
    expect((await res.json()).error).toBe('blocked_input');
  });

  it('POST /prompt/validate (verify wizard) bloque', async () => {
    const res = await validate(req({ prompt: `Instructions. ${KEYLOGGER}` }));
    expect(res.status).toBe(422);
    expect((await res.json()).error).toBe('blocked_input');
  });

  it('POST /prompt/assist bloque', async () => {
    const res = await assist(req({ prompt: KEYLOGGER }));
    expect(res.status).toBe(422);
  });

  it('POST /prompt/optimize bloque', async () => {
    const res = await optimize(req({ prompt: KEYLOGGER }));
    expect(res.status).toBe(422);
  });

  it('POST /prompt/suggest-starters bloque', async () => {
    const res = await suggestStarters(req({ prompt: `Système. ${KEYLOGGER}` }));
    expect(res.status).toBe(422);
  });

  it('POST /onboarding/chat bloque le dernier message utilisateur', async () => {
    const res = await onboardingChat(req({ messages: [{ role: 'user', content: KEYLOGGER }] }));
    expect(res.status).toBe(422);
  });

  it('POST /agents/[id]/chat bloque le dernier message utilisateur', async () => {
    const res = await agentChat(req({ messages: [{ role: 'user', content: KEYLOGGER }] }), {
      params: Promise.resolve({ id: 'agent-1' }),
    });
    expect(res.status).toBe(422);
  });
});

describe('garde au niveau des routes — blocage de la SORTIE (keylogger généré)', () => {
  it('POST /prompt/assist bloque la sortie (422 blocked_output)', async () => {
    ctl.generation = `Voici le prompt :\n<script>${KEYLOGGER}</script>`;
    const res = await assist(req({ prompt: 'Aide-moi à écrire un prompt.' }));
    expect(res.status).toBe(422);
    expect((await res.json()).error).toBe('blocked_output');
  });

  it('POST /prompt/suggest-starters bloque la sortie', async () => {
    ctl.generation = `{"greeting":"<script>${KEYLOGGER}</script>","examples":["a"]}`;
    const res = await suggestStarters(req({ prompt: BENIGN_SYSTEM }));
    expect(res.status).toBe(422);
    expect((await res.json()).error).toBe('blocked_output');
  });
});

describe('garde au niveau des routes — le contenu BÉNIN passe', () => {
  it('POST /prompt/validate accepte un prompt système légitime (200 ok)', async () => {
    const res = await validate(req({ prompt: BENIGN_SYSTEM }));
    expect(res.status).toBe(200);
    expect((await res.json()).ok).toBe(true);
  });

  it('POST /prompt/assist renvoie le prompt généré bénin (200)', async () => {
    ctl.generation = 'Rôle : assistant juridique. Public : agents. Ton : formel. Contraintes : citer les textes.';
    const res = await assist(req({ prompt: 'Aide-moi.' }));
    expect(res.status).toBe(200);
    expect((await res.json()).prompt).toContain('assistant juridique');
  });
});
