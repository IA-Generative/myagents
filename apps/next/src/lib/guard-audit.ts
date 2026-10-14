// Persistance des alertes du garde anti-prompt-injection (server-only).
//
// `recordGuardEvent` journalise un blocage à deux endroits :
//   1. console structurée (via logGuardEvent — testable, sans dépendance DB) ;
//   2. table dédiée `ab_guard_events` (la « file d'audit » : heure + utilisateur
//      + signaux), pour audit / pen-test.
//
// IMPORTANT : l'écriture en base est NON BLOQUANTE. Un échec de persistance ne
// doit jamais faire échouer la requête utilisateur (le blocage prime sur l'audit).
// Ce module importe Prisma ; il est donc séparé de prompt-guard.ts, qui reste
// pur et partagé avec le harnais de tests.

import { prisma } from './db';
import {
  logGuardEvent,
  type Signal,
  type Severity,
  type AuditSink,
  type GuardEventInput,
} from './prompt-guard';

/** Sévérité la plus élevée parmi les signaux ayant déclenché (défaut: medium). */
function highestSeverity(signals: Signal[]): Severity {
  return signals.some((s) => s.complied && s.severity === 'high') ? 'high' : 'medium';
}

export async function recordGuardEvent(event: GuardEventInput): Promise<void> {
  // 1. Console (comportement existant, conservé).
  logGuardEvent(event);

  const fired = event.signals.filter((s) => s.complied);
  if (fired.length === 0) return;

  // 2. Persistance en base — best-effort, jamais bloquant.
  try {
    await prisma.guardEvent.create({
      data: {
        userId: event.userId ?? null,
        route: event.route,
        stage: event.stage,
        role: event.role ?? null,
        severity: highestSeverity(fired),
        signals: fired.map((s) => ({
          source: s.source,
          severity: s.severity,
          reason: s.reason,
        })),
      },
    });
  } catch (err) {
    console.error('[guard-audit] échec persistance GuardEvent (non bloquant):', err);
  }
}

/**
 * Puits d'audit Prisma : implémentation du contrat `AuditSink` du composant
 * prompt-guard. C'est l'adapter de persistance que l'app injecte (le cœur reste
 * agnostique de la base de données).
 */
export const prismaAuditSink: AuditSink = {
  record: recordGuardEvent,
};
