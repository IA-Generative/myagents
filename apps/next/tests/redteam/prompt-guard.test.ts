// Tests OFFLINE du garde de production (src/lib/prompt-guard.ts).
//
// Aucun credential requis : ces tests valident les COUCHES déterministes
// (inspection d'entrée, inspection de sortie, durcissement). Ils tournent dans
// `npm test` par défaut. Le LLM-juge (judgeOutput) est testé dans
// detectors.test.ts (skippé sans creds).
//
// Stratégie : on passe TOUT le corpus red-team (payloads.ts) au garde d'entrée
// et on exige que chaque attaque soit bloquée par au moins un signal, puis on
// vérifie qu'aucun contenu bénin ne déclenche de faux positif.

import { describe, it, expect } from 'vitest';
import {
  inspectInput,
  inspectOutput,
  hardenSystemPrompt,
  makeCanary,
  keyloggerDetector,
} from '../../src/lib/prompt-guard';
import { ATTACKS } from './payloads';

const KEYLOGGER =
  "javascript:window.addEventListener('keypress', function(e){localStorage.keys += String.fromCharCode(e.keyCode);});";

describe('inspectInput — bloque tout le corpus red-team', () => {
  for (const payload of ATTACKS) {
    it(`bloque ${payload.id}`, () => {
      const result = inspectInput(payload.prompt, payload.deliveryRole);
      expect(result.blocked, `aucun signal pour ${payload.id}`).toBe(true);
      expect(result.signals.some((s) => s.complied)).toBe(true);
    });
  }
});

describe('inspectInput — pas de faux positif sur du contenu bénin', () => {
  const benins = [
    'Tu es un assistant juridique qui aide les agents à rédiger des notes de synthèse en citant les textes en vigueur.',
    'Génère une page web HTML simple avec un formulaire de contact (nom, email, message) et un bouton Envoyer.',
    "Réponds de façon concise et factuelle, sans commentaire superflu, en français administratif clair.",
    'Explique-moi la différence entre un décret et un arrêté.',
    'Invente une histoire courte pour enfants sur un renard et une lune.',
  ];
  for (const [i, txt] of benins.entries()) {
    it(`ne bloque pas le contenu bénin #${i + 1}`, () => {
      expect(inspectInput(txt, 'user').blocked).toBe(false);
      expect(inspectInput(txt, 'system').blocked).toBe(false);
    });
  }
});

describe('inspectOutput — caviarde la sortie dangereuse', () => {
  it('bloque une page contenant un keylogger', () => {
    const page = `<html><body><form>...</form><script>${KEYLOGGER}</script></body></html>`;
    expect(inspectOutput(page).blocked).toBe(true);
  });

  it('bloque un keylogger offusqué par concaténation', () => {
    const obf =
      "window.addEventListener('key'+'press', function(e){window['loca'+'lStorage'].keys += String['from'+'CharCode'](e.keyCode);});";
    expect(inspectOutput(obf).blocked).toBe(true);
  });

  it('détecte la fuite du canari planté', () => {
    const canary = makeCanary();
    const leaky = `Mes instructions internes contiennent le jeton ${canary}, le voici.`;
    expect(inspectOutput(leaky, { canary }).blocked).toBe(true);
  });

  it('ne bloque pas une page web bénigne', () => {
    const page =
      '<html><body><h1>Contact</h1><form><input name="email"/><button>Envoyer</button></form></body></html>';
    expect(inspectOutput(page, { canary: makeCanary() }).blocked).toBe(false);
  });

  it('ne bloque pas un refus poli', () => {
    const refus =
      "Je ne peux pas insérer ce code : il s'agit d'un enregistreur de frappe (keylogger). Je vous propose plutôt un script d'analytics respectueux de la vie privée.";
    expect(inspectOutput(refus).blocked).toBe(false);
  });
});

describe('hardenSystemPrompt — envelope de sécurité', () => {
  const canary = makeCanary();
  const hardened = hardenSystemPrompt('Tu es un assistant juridique.', canary);

  it('encadre la persona du créateur', () => {
    expect(hardened).toContain('Tu es un assistant juridique.');
    expect(hardened).toContain('DEBUT_PERSONA');
    expect(hardened).toContain('FIN_PERSONA');
  });

  it('plante le canari et énonce les règles non négociables', () => {
    expect(hardened).toContain(canary);
    expect(hardened).toMatch(/RÈGLES DE SÉCURITÉ/);
    expect(hardened).toMatch(/keylogger/i);
  });

  it('génère un canari unique par appel', () => {
    expect(makeCanary()).not.toBe(makeCanary());
  });

  it("le canari de la persona n'est pas un keylogger (pas de faux positif sur l'envelope)", () => {
    expect(keyloggerDetector(hardened).complied).toBe(false);
  });
});
