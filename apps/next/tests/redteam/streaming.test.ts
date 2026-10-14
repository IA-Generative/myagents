// Tests OFFLINE de l'inspecteur de sortie en streaming (emprunt NeMo : output
// rails par fenêtre glissante). Aucun appel réseau.

import { describe, it, expect } from 'vitest';
import { createStreamingOutputInspector, makeCanary } from '../../src/lib/prompt-guard';

const KEYLOGGER =
  "window.addEventListener('keypress', function(e){localStorage.keys += String.fromCharCode(e.keyCode);});";

describe('createStreamingOutputInspector', () => {
  it('détecte une signature scindée EN PLEIN MILIEU sur deux fragments', () => {
    const insp = createStreamingOutputInspector();
    // On coupe au milieu de « String.fromCharCode » : aucun fragment ne porte de
    // signature complète, mais la jonction (contexte reporté) la reconstitue.
    const r1 = insp.push('<p>extrait analytics</p> String.fromChar');
    expect(r1.blocked).toBe(false);
    const r2 = insp.push('Code(e.keyCode);</script>');
    expect(r2.blocked).toBe(true);
    expect(insp.done().blocked).toBe(true);
  });

  it('ne bloque pas un flux bénin', () => {
    const insp = createStreamingOutputInspector();
    for (const chunk of ['<html>', '<body>', '<h1>Contact</h1>', '<form>', '</form>', '</body></html>']) {
      expect(insp.push(chunk).blocked).toBe(false);
    }
    expect(insp.done().blocked).toBe(false);
  });

  it('détecte une fuite du canari en milieu de flux', () => {
    const canary = makeCanary();
    const insp = createStreamingOutputInspector({ canary });
    expect(insp.push('Voici la réponse, ').blocked).toBe(false);
    expect(insp.push(`mon jeton interne est ${canary}, oups.`).blocked).toBe(true);
  });

  it('latch : reste bloqué une fois déclenché', () => {
    const insp = createStreamingOutputInspector();
    insp.push('<script>' + KEYLOGGER + '</script>');
    expect(insp.push(' texte anodin ensuite').blocked).toBe(true);
  });
});
