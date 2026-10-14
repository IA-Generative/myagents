// @mirai/prompt-guard — composant réutilisable de garde anti-prompt-injection
// (OWASP LLM01). API publique.
//
// Architecture (voir docs/prompt-guard-isolation.md) :
//   core   — heuristiques pures + durcissement + messages (zéro dépendance)
//   judge  — LLM-juge via interface `LLMJudge` injectable (fournisseur-agnostique)
//   audit  — `AuditSink` injectable (console par défaut ; Prisma côté app)
//   config — réglages (modèle juge, couches, fail-closed)
//
// L'application branche le fournisseur LLM et la persistance via des adapters
// (cf. src/lib/prompt-guard.ts et src/lib/guard-audit.ts), de sorte que le cœur
// reste testable hors-ligne et réutilisable dans un autre contexte.

export * from './core';
export * from './judge';
export * from './audit';
export * from './config';
