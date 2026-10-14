// Menu commun de la bêta (dépôt IA-Generative/mirai-apps-menu) : servi par le même hôte sous
// /_beta, à travers un Ingress posé hors de ce dépôt. Il porte le compte (bulle aux initiales,
// déconnexion), l'en-tête de l'application n'en affiche donc plus. Absent (dev local, hôte
// sans /_beta) : rien ne s'affiche et rien ne casse.

declare global {
  interface Window {
    MIRAI_MENU?: Record<string, unknown>
  }
}

export interface IdentiteMenu {
  id: string
  username: string
  email: string
}

export function chargerMenuCommun(): void {
  // Le serveur Vite répondrait index.html à la place du script : pas de menu en dev.
  if (import.meta.env.DEV) return
  // `sortie` : la table APPS du menu la connaît pour l'hôte mesagents ; posée ici aussi pour
  // les hôtes qu'elle ne connaît pas (previews myagents-pr-<n>).
  window.MIRAI_MENU = { sortie: '/deconnexion', ...window.MIRAI_MENU }
  // Ajouté par script et non dans index.html : la CSP (script-src 'self') refuse l'attribut
  // onerror en ligne que propose le contrat d'intégration du menu.
  const script = document.createElement('script')
  script.src = '/_beta/menu.js'
  script.async = true
  script.onerror = () => {}
  document.body.appendChild(script)
}

// Le menu ne lit aucun jeton : l'identité vient de l'application. `sub` fait de la cloche et
// des avis la boîte de la personne, la même sur toutes les applications de la bêta.
export function annoncerIdentite(user: IdentiteMenu | null): void {
  if (!user) return
  window.MIRAI_MENU = { ...window.MIRAI_MENU, sub: user.id, nom: user.username, mail: user.email }
  document.dispatchEvent(
    new CustomEvent('mirai-menu:identite', { detail: { nom: user.username, mail: user.email } }),
  )
}
