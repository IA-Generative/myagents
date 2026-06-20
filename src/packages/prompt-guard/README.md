# @mirai/prompt-guard

Composant réutilisable de **garde anti-prompt-injection** (OWASP LLM01), à cœur
pur et sans dépendance applicative. Défense en profondeur, 3 couches :

1. `inspectInput(text, role)` — heuristiques sur le contenu entrant (marqueurs
   d'injection connus, code keylogger brut/offusqué).
2. `hardenSystemPrompt(persona, canary)` — envelope de *spotlighting* + règles
   non-négociables + canari.
3. `inspectOutput(text, { canary })` + `judgeWith(judge, { goal, response })` —
   inspection de la sortie (signatures, fuite du canari) + LLM-juge injectable.
   Fail-closed.

## Caractéristiques

- **Pur** : `core` ne dépend que de `node:crypto`. Aucun import LLM/DB/Next.
- **Fournisseur LLM injectable** via l'interface `LLMJudge` (`judge.ts`).
- **Audit injectable** via l'interface `AuditSink` (`audit.ts`).
- **Configurable** via `GuardConfig` (`config.ts`) : modèle juge, couches,
  fail-closed.

## Utilisation

```ts
import {
  inspectInput, hardenSystemPrompt, makeCanary, inspectOutput,
  judgeWith, DEFAULT_OUTPUT_POLICY_GOAL, type LLMJudge,
} from '@mirai/prompt-guard';

const myJudge: LLMJudge = { complete: async ({ system, user }) => callMyLLM(system, user) };

const inGuard = inspectInput(userText, 'user');
if (inGuard.blocked) return block();

const canary = makeCanary();
const system = hardenSystemPrompt(persona, canary);
const answer = await callMyLLM(system, userText);

const out = inspectOutput(answer, { canary });
const verdict = await judgeWith(myJudge, { goal: DEFAULT_OUTPUT_POLICY_GOAL, response: answer });
if (out.blocked || verdict.complied) return block();
```

## Intégration dans cette app

- `src/lib/prompt-guard.ts` — adapter Scaleway (implémente `LLMJudge`,
  ré-exporte tout, expose `judgeOutput` historique).
- `src/lib/guard-audit.ts` — adapter Prisma (`prismaAuditSink`).

Voir [`docs/prompt-guard-isolation.md`](../../../docs/prompt-guard-isolation.md)
pour la spécification complète et le choix du modèle juge (coût vs détection).
