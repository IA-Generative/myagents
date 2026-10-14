// Rendu des réponses des agents : Markdown → HTML assaini.
//
// La réponse vient d'un modèle de langage, donc potentiellement d'un contenu injecté (prompt
// injection) : tout passe par DOMPurify avec une liste BLANCHE de balises. Pas d'image (une
// image distante est le canal classique d'exfiltration : ![](https://…?donnees=…)), pas de
// HTML brut, pas de formulaire ; les liens s'ouvrent dans un nouvel onglet, sans référent.
import DOMPurify from 'dompurify'
import { Marked } from 'marked'

const markdown = new Marked({ gfm: true, breaks: true, async: false })

const ALLOWED_TAGS = [
  'p', 'br', 'strong', 'em', 'del', 'code', 'pre', 'blockquote', 'hr',
  'ul', 'ol', 'li', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
]
const ALLOWED_ATTR = ['href', 'title', 'start']

const purify = DOMPurify()
purify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function renderMarkdown(text: string): string {
  const html = markdown.parse(text ?? '') as string
  return purify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: [...ALLOWED_ATTR, 'target', 'rel'],
    ALLOWED_URI_REGEXP: /^(?:https?:|mailto:)/i,
  })
}
