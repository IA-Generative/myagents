// Banc d'essai red-team : tire le corpus d'attaques contre le modèle brut
// (scwChatCompletions) et vérifie qu'il RÉSISTE.
//
// OPT-IN : sans SCW_SECRET_KEY_LLM la suite entière est skippée, donc
// `npm test` reste vert et hors-ligne. Lancer explicitement via
// `npm run test:redteam` après avoir renseigné .env.test.local.
//
// Chaque payload est tiré SAMPLES fois (worst-case) : l'attaque échoue dès
// qu'UN tirage cède.

import { describe, it, expect } from 'vitest';
import { scwChatCompletions } from '../../src/lib/scw-llm-client';
import { ATTACKS } from './payloads';
import { scoreAttack, type Signal } from './detectors';
import { buildRawMessages } from './harness';

const HAS_CREDS =
  Boolean(process.env.SCW_LLM_BASE_URL) && Boolean(process.env.SCW_SECRET_KEY_LLM);

const SAMPLES = Number(process.env.REDTEAM_SAMPLES ?? '3');
// Modèles à tester (défaut : modèle configuré côté serveur). Plusieurs séparés par virgule.
const MODELS = (process.env.REDTEAM_MODELS ?? process.env.SCW_LLM_MODEL ?? 'gpt-oss-120b')
  .split(',')
  .map((m) => m.trim())
  .filter(Boolean);

function formatSignals(signals: Signal[]): string {
  return signals
    .map((s) => `    [${s.complied ? 'CÉDÉ' : 'ok'}] ${s.source}: ${s.reason}`)
    .join('\n');
}

describe.skipIf(!HAS_CREDS)('red-team — résistance aux prompt injections', () => {
  for (const model of MODELS) {
    describe(`modèle ${model}`, () => {
      for (const payload of ATTACKS) {
        it(`résiste à ${payload.id} [${payload.category}/${payload.severity}]`, async () => {
          const { messages, canary } = buildRawMessages(payload);

          // SAMPLES tirages concurrents.
          const runs = await Promise.all(
            Array.from({ length: SAMPLES }, async (_, i) => {
              const completion = await scwChatCompletions({ model, messages });
              const response = completion.choices?.[0]?.message?.content ?? '';
              const score = await scoreAttack({ payload, response, canary });
              return { i, response, ...score };
            }),
          );

          const breached = runs.filter((r) => !r.resisted);

          if (breached.length > 0) {
            const detail = breached
              .map(
                (r) =>
                  `  Tirage #${r.i} a CÉDÉ:\n${formatSignals(r.signals)}\n    Réponse: ${r.response.slice(0, 400)}`,
              )
              .join('\n');
            expect.fail(
              `Le modèle ${model} a cédé à ${payload.id} sur ${breached.length}/${SAMPLES} tirages.\n${detail}`,
            );
          }

          expect(breached.length).toBe(0);
        });
      }
    });
  }
});

if (!HAS_CREDS) {
  // Visibilité : on signale pourquoi la suite est vide plutôt que de la cacher.
  describe('red-team', () => {
    it.skip('skippé — SCW_LLM_BASE_URL / SCW_SECRET_KEY_LLM absents (voir tests/redteam/README.md)', () => {});
  });
}
