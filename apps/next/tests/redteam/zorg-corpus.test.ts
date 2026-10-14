// Tests OFFLINE du générateur de corpus ZORG.
//
// Valide les invariants STRUCTURELS du corpus généré (pas d'appel réseau) :
// identifiants uniques, prompts non vides, métadonnées de synthèse présentes.
// NB : on n'exige PAS que la garde bloque tous les payloads ZORG à l'entrée —
// c'est justement ce que la matrice live mesure (certaines techniques visent à
// passer la couche 1 pour être rattrapées en sortie / par le juge).

import { describe, it, expect } from 'vitest';
import { ZORG_ATTACKS, buildZorgCorpus } from './zorg-corpus';

describe('corpus ZORG — invariants structurels', () => {
  it('génère un corpus non vide et déterministe', () => {
    expect(ZORG_ATTACKS.length).toBeGreaterThan(20);
    // Déterministe : deux générations produisent les mêmes identifiants.
    expect(buildZorgCorpus().map((a) => a.id)).toEqual(ZORG_ATTACKS.map((a) => a.id));
  });

  it('a des identifiants uniques', () => {
    const ids = ZORG_ATTACKS.map((a) => a.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('renseigne les métadonnées de synthèse sur chaque payload', () => {
    for (const a of ZORG_ATTACKS) {
      expect(a.prompt.trim().length).toBeGreaterThan(50);
      expect(a.goal.trim().length).toBeGreaterThan(10);
      expect(a.source).toBe('zorg');
      expect(a.lang === 'fr' || a.lang === 'en').toBe(true);
      expect(a.axes && a.axes.length).toBeGreaterThan(0);
      expect(['keylogger', 'disinfo', 'prompt-leak']).toContain(a.goalKind);
      // Toujours au moins les techniques d'enveloppe ZORG.
      expect(a.axes).toContain('persona-hijack');
      expect(a.axes).toContain('refusal-suppression');
    }
  });

  it('couvre les deux langues, les trois objectifs et les deux rôles', () => {
    const langs = new Set(ZORG_ATTACKS.map((a) => a.lang));
    const goals = new Set(ZORG_ATTACKS.map((a) => a.goalKind));
    const roles = new Set(ZORG_ATTACKS.map((a) => a.deliveryRole));
    expect(langs).toEqual(new Set(['fr', 'en']));
    expect(goals).toEqual(new Set(['keylogger', 'disinfo', 'prompt-leak']));
    expect(roles).toEqual(new Set(['user', 'system']));
  });

  it('réserve prompt-leak à la livraison utilisateur', () => {
    const leak = ZORG_ATTACKS.filter((a) => a.goalKind === 'prompt-leak');
    expect(leak.length).toBeGreaterThan(0);
    expect(leak.every((a) => a.deliveryRole === 'user')).toBe(true);
  });
});
