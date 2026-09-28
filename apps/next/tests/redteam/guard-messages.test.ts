// Tests OFFLINE des messages utilisateur + de la logique de l'endpoint de
// validation du wizard (POST /api/ab/prompt/validate).
//
// L'endpoint applique exactement inspectInput(prompt, 'system') ; on teste donc
// cette logique directement (déterministe, sans credential ni DB).

import { describe, it, expect } from 'vitest';
import {
  inspectInput,
  BLOCK_MESSAGE_USER_INPUT,
  BLOCK_MESSAGE_AGENT_CONFIG,
  BLOCK_MESSAGE_OUTPUT,
} from '../../src/lib/prompt-guard';
import { ATTACKS } from './payloads';

const EMOJI = /\p{Extended_Pictographic}/u;

describe('messages de blocage (ton sobre)', () => {
  const messages = {
    BLOCK_MESSAGE_USER_INPUT,
    BLOCK_MESSAGE_AGENT_CONFIG,
    BLOCK_MESSAGE_OUTPUT,
  };
  for (const [name, msg] of Object.entries(messages)) {
    it(`${name} est non vide, en français, sans emoji`, () => {
      expect(typeof msg).toBe('string');
      expect(msg.trim().length).toBeGreaterThan(20);
      expect(EMOJI.test(msg)).toBe(false);
      expect(msg).toContain('autorisé'); // formulation commune « pas autorisé »
    });
  }
});

describe('validation wizard — inspectInput(prompt, "system")', () => {
  it('bloque un prompt système porteur d\'une attaque (cas A1-keylogger-system)', () => {
    const attack = ATTACKS.find((a) => a.id === 'A1-keylogger-system');
    expect(attack).toBeDefined();
    const r = inspectInput(attack!.prompt, 'system');
    expect(r.blocked).toBe(true);
    expect(r.signals.some((s) => s.complied)).toBe(true);
  });

  it('autorise un prompt système ministériel légitime', () => {
    const benin =
      'Tu es un assistant juridique pour les agents de la DLPAJ. Tu rédiges des notes ' +
      'structurées, cites systématiquement les textes en vigueur, et ne fabriques jamais ' +
      'de sources. Public : agents de préfecture. Ton : formel et précis.';
    expect(inspectInput(benin, 'system').blocked).toBe(false);
  });
});
