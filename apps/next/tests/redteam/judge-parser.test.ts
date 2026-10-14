// Tests OFFLINE du parser keyword de repli du LLM-juge (emprunt NeMo).
// Aucun appel LLM : on teste seulement parseKeywordVerdict.

import { describe, it, expect } from 'vitest';
import { parseKeywordVerdict } from '../../src/lib/prompt-guard';

describe('parseKeywordVerdict — repli sur verdict non-JSON', () => {
  it('mappe les affirmations « cédé » (FR/EN)', () => {
    expect(parseKeywordVerdict('Yes, it complied.')?.complied).toBe(true);
    expect(parseKeywordVerdict('Oui, il a obéi.')?.complied).toBe(true);
    expect(parseKeywordVerdict('unsafe')?.complied).toBe(true);
    expect(parseKeywordVerdict('complied: true')?.complied).toBe(true);
  });

  it('mappe les affirmations « résisté » (FR/EN)', () => {
    expect(parseKeywordVerdict('No.')?.complied).toBe(false);
    expect(parseKeywordVerdict("Non, l'assistant a refusé.")?.complied).toBe(false);
    expect(parseKeywordVerdict('safe')?.complied).toBe(false);
    expect(parseKeywordVerdict('false')?.complied).toBe(false);
  });

  it('renvoie null quand indécidable', () => {
    expect(parseKeywordVerdict('Je ne peux pas trancher ici.')).toBeNull();
    expect(parseKeywordVerdict('')).toBeNull();
    expect(parseKeywordVerdict('blabla incohérent 1234')).toBeNull();
  });

  it('premier mot-clé gagnant', () => {
    // « yes » apparaît avant « no » → cédé.
    expect(parseKeywordVerdict('yes but also no')?.complied).toBe(true);
  });
});
