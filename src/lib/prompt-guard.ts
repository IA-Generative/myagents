// Garde anti-prompt-injection (OWASP LLM01) — ADAPTER APPLICATIF.
//
// La logique vit désormais dans le composant réutilisable
// `src/packages/prompt-guard` (cœur pur + juge injectable + audit injectable).
// Ce fichier est l'adapter Next/Scaleway : il ré-exporte l'API publique du
// composant et branche le LLM-juge sur le client Scaleway, de sorte que les
// routes et le harnais red-team continuent d'importer `@/lib/prompt-guard`
// exactement comme avant (API inchangée).

import { scwChatCompletions } from './scw-llm-client';
import { judgeWith, resolveJudgeModel, type LLMJudge } from '../packages/prompt-guard';

// Ré-export de toute l'API publique du composant (core + judge + audit + config).
export * from '../packages/prompt-guard';

/**
 * Adapter juge Scaleway : le composant est agnostique du fournisseur LLM, on lui
 * injecte ici le client souverain. Température 0 + budget court : verdict
 * déterministe et économe.
 */
const scwJudge: LLMJudge = {
  async complete({ system, user, model, temperature, maxTokens }) {
    const completion = await scwChatCompletions({
      model,
      temperature: temperature ?? 0,
      maxTokens: maxTokens ?? 512,
      messages: [
        { role: 'system', content: system },
        { role: 'user', content: user },
      ],
    });
    return completion.choices?.[0]?.message?.content ?? '';
  },
};

/**
 * LLM-juge inline de production (API historique conservée). Classe si une
 * réponse a obéi à un objectif malveillant. Fail-closed.
 */
export function judgeOutput(params: {
  goal: string;
  response: string;
  model?: string;
}): Promise<{ complied: boolean; reason: string }> {
  return judgeWith(scwJudge, { ...params, model: resolveJudgeModel(params.model) });
}
