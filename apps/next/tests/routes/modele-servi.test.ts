// Régression de la panne du 2026-09-23 : « Mes agents » rendait 502
// `upstream_failure` sur CHAQUE message de cinq agents sur dix. Cause : leur
// instantané de configuration gardait `mistral-small-3.2-24b-instruct-2506`,
// nom retiré du catalogue le 2026-08-25 — le hub répondait 400 « Invalid model
// name », que la route traduisait en 502 (un message qui accuse le réseau).
//
// Ce que ce fichier prouve, hors ligne (le catalogue du hub est simulé) :
//   1. un nom disparu n'est PAS envoyé au hub — on retombe sur l'alias ;
//   2. un nom servi passe intact ;
//   3. catalogue injoignable → on n'invente rien (échec OUVERT) : une panne du
//      catalogue ne doit pas changer le modèle de tous les agents en silence ;
//   4. le défaut du wizard est un nom que le hub sert vraiment.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const CATALOGUE = ['chat', 'chat-pro', 'vision', 'tools', 'gptoss-120b'];
const DISPARU = 'mistral-small-3.2-24b-instruct-2506';

function poserEnv() {
  process.env.SCW_LLM_BASE_URL = 'https://hub-de-test.invalid/v1';
  process.env.SCW_SECRET_KEY_LLM = 'jeton-de-test';
  process.env.SCW_LLM_MODEL = 'chat';
}

// Le cache du catalogue vit une heure dans le module : on réimporte à chaque
// cas pour que chacun parte d'une ardoise propre.
async function clientNeuf(fetchMock: typeof fetch) {
  vi.resetModules();
  poserEnv();
  vi.stubGlobal('fetch', fetchMock);
  return import('@/lib/scw-llm-client');
}

const catalogueOk = (async () =>
  new Response(JSON.stringify({ data: CATALOGUE.map((id) => ({ id })) }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })) as unknown as typeof fetch;

const catalogueMuet = (async () => {
  throw new Error('hub injoignable');
}) as unknown as typeof fetch;

describe('le modèle demandé est confronté au catalogue réellement servi', () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it('un nom disparu du catalogue n’est pas envoyé au hub', async () => {
    const { resolveServedModel } = await clientNeuf(catalogueOk);
    // `undefined` = « laisse le client prendre l'alias SCW_LLM_MODEL ».
    await expect(resolveServedModel(DISPARU)).resolves.toBeUndefined();
  });

  it('un nom encore servi passe intact', async () => {
    const { resolveServedModel } = await clientNeuf(catalogueOk);
    await expect(resolveServedModel('chat-pro')).resolves.toBe('chat-pro');
  });

  it('catalogue injoignable : on n’invente rien, le nom demandé passe', async () => {
    const { resolveServedModel } = await clientNeuf(catalogueMuet);
    await expect(resolveServedModel('un-modele-quelconque')).resolves.toBe(
      'un-modele-quelconque',
    );
  });

  it('un instantané sans modèle retombe sur l’alias configuré', async () => {
    const { resolveServedModel } = await clientNeuf(catalogueOk);
    await expect(resolveServedModel(null)).resolves.toBeUndefined();
    await expect(resolveServedModel(undefined)).resolves.toBeUndefined();
  });

  it('le catalogue n’est interrogé qu’une fois (cache)', async () => {
    const espion = vi.fn(catalogueOk as never);
    const { resolveServedModel } = await clientNeuf(espion as unknown as typeof fetch);
    await resolveServedModel('chat');
    await resolveServedModel('vision');
    expect(espion).toHaveBeenCalledTimes(1);
  });
});

// --- Publication dans Mon assistant ---------------------------------------
// Le socle n'expose qu'une PARTIE du hub : un modèle peut répondre au banc
// d'essai de Mes agents et rester introuvable une fois l'agent publié
// (« Model not found »). C'est le catalogue du socle qui fait foi ici.
const SOCLE = ['chat', 'chat-pro', 'vision', 'tools', 'openrag-demo-teletravail'];
const SERVI_PAR_LE_HUB_SEUL = 'gptoss-120b';

const socleOk = (async () =>
  new Response(JSON.stringify({ data: SOCLE.map((id) => ({ id })) }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })) as unknown as typeof fetch;

async function adminNeuf(fetchMock: typeof fetch) {
  vi.resetModules();
  poserEnv();
  process.env.OWUI_BASE_URL = 'http://socle-de-test.invalid';
  process.env.OWUI_ADMIN_API_KEY = 'cle-de-test';
  vi.stubGlobal('fetch', fetchMock);
  return import('@/lib/owui-admin-client');
}

describe('le modèle publié dans Mon assistant', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('remplace un modèle que le socle ne sert pas (la fiche serait morte)', async () => {
    const { resolveOwuiBaseModel } = await adminNeuf(socleOk);
    await expect(resolveOwuiBaseModel(DISPARU, 'chat')).resolves.toBe('chat');
  });

  it('remplace aussi un modèle servi par le HUB mais absent du socle', async () => {
    const { resolveOwuiBaseModel } = await adminNeuf(socleOk);
    await expect(resolveOwuiBaseModel(SERVI_PAR_LE_HUB_SEUL, 'chat')).resolves.toBe('chat');
  });

  it('laisse intact un modèle que le socle sert', async () => {
    const { resolveOwuiBaseModel } = await adminNeuf(socleOk);
    await expect(resolveOwuiBaseModel('chat-pro', 'chat')).resolves.toBe('chat-pro');
  });

  it('socle injoignable : on publie le choix de l’auteur, sans rien inventer', async () => {
    const { resolveOwuiBaseModel } = await adminNeuf(catalogueMuet);
    await expect(resolveOwuiBaseModel('un-modele-quelconque', 'chat')).resolves.toBe(
      'un-modele-quelconque',
    );
  });

  it('un agent sans modèle choisi part sur l’alias par défaut', async () => {
    const { resolveOwuiBaseModel } = await adminNeuf(socleOk);
    await expect(resolveOwuiBaseModel(null, 'chat')).resolves.toBe('chat');
  });
});

describe('le défaut proposé par le wizard', () => {
  it('est un alias que le hub sert', async () => {
    const { DEFAULT_MODEL_ID } = await import('@/lib/models');
    expect(CATALOGUE).toContain(DEFAULT_MODEL_ID);
  });

  it('n’est jamais un nom daté (ceux-là disparaissent aux renommages)', async () => {
    const { DEFAULT_MODEL_ID } = await import('@/lib/models');
    expect(DEFAULT_MODEL_ID).not.toMatch(/\d{4}|\d+b-/i);
  });
});
