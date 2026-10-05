import { afterEach, describe, expect, it, vi } from 'vitest'
import { annoncerIdentite } from './menuCommun'

describe('annoncerIdentite', () => {
  afterEach(() => {
    delete window.MIRAI_MENU
  })

  it("passe nom, courriel et sub au menu commun sans écraser sa sortie", () => {
    window.MIRAI_MENU = { sortie: '/deconnexion' }
    const recu = vi.fn()
    document.addEventListener('mirai-menu:identite', recu)

    annoncerIdentite({ id: 'sub-1', username: 'alice', email: 'alice@example.org' })

    expect(window.MIRAI_MENU).toEqual({
      sortie: '/deconnexion',
      sub: 'sub-1',
      nom: 'alice',
      mail: 'alice@example.org',
    })
    expect(recu).toHaveBeenCalledOnce()
    expect((recu.mock.calls[0][0] as CustomEvent).detail).toEqual({
      nom: 'alice',
      mail: 'alice@example.org',
    })
    document.removeEventListener('mirai-menu:identite', recu)
  })

  it("ne fait rien tant que l'utilisateur est inconnu", () => {
    const recu = vi.fn()
    document.addEventListener('mirai-menu:identite', recu)

    annoncerIdentite(null)

    expect(recu).not.toHaveBeenCalled()
    expect(window.MIRAI_MENU).toBeUndefined()
    document.removeEventListener('mirai-menu:identite', recu)
  })
})
