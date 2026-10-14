// @mirai/prompt-guard — PUITS D'AUDIT injectable.
//
// Le composant journalise les blocages via un `AuditSink`. L'implémentation par
// défaut (`ConsoleAuditSink`) écrit sur la console (cf. logGuardEvent du cœur) ;
// l'application fournit son propre puits pour persister (ex. Prisma dans
// src/lib/guard-audit.ts) sans coupler le cœur à une base de données.

import { logGuardEvent, type Signal } from './core';

export type GuardEventInput = {
  route: string;
  stage: 'input' | 'output' | 'validate';
  userId?: string;
  role?: 'user' | 'system';
  signals: Signal[];
};

/**
 * Contrat d'un puits d'audit. `record` ne doit JAMAIS lever : un échec de
 * persistance ne doit pas faire échouer la requête utilisateur (le blocage prime
 * sur l'audit).
 */
export interface AuditSink {
  record(event: GuardEventInput): Promise<void> | void;
}

/** Puits par défaut : journalise sur la console structurée du cœur. */
export const ConsoleAuditSink: AuditSink = {
  record(event) {
    logGuardEvent(event);
  },
};
