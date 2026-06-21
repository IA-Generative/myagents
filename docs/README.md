# Documentation — MirAI Agent Builder

Point d'entrée de toute la documentation du dépôt. Le code vit sous `app/` et
`src/` ; tout le déploiement sous `deploy/` (scripts, `k8s/`, `keycloak/`).

## Spécifications produit — [`specs/`](specs/)

| Document | Rôle |
|----------|------|
| [specs/agent-builder-spec.md](specs/agent-builder-spec.md) | Spec fonctionnelle de référence (§1 à §10) — la source de vérité produit. |
| [specs/agent-builder-roadmap-v2.md](specs/agent-builder-roadmap-v2.md) | Extensions V2 additives (5 extensions) qui prolongent la spec sans la réécrire. |

## Architecture & sécurité

| Document | Rôle |
|----------|------|
| [prompt-guard-isolation.md](prompt-guard-isolation.md) | Extraction de la garde anti-injection dans un module autonome `src/packages/prompt-guard`. |
| [nemo-guardrails-comparison.md](nemo-guardrails-comparison.md) | Comparatif NVIDIA NeMo Guardrails ↔ module `@mirai/prompt-guard` interne. |

## Maquettes — [`mockups/`](mockups/)

6 écrans DSFR (paires HTML + PNG) issus de la phase de design V2 : wizard
« Actions », enregistrement, panneau overlay, progression d'exécution, cartes
« Mes Agents », onglet « Apprendre ».

---

> **Note** — les notes de sécurité opérationnelles (audit pré-pentest, plan de
> remédiation) restent volontairement hors dépôt, dans `private/` (gitignoré),
> aux côtés des secrets ; elles ne sont pas publiées ici.
