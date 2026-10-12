# Veilles — collecte sur les sites autorisés

La capacité `web.collecter` (kind `http`, point d'accès interne `interne:web.collecter`, lecture seule, monde ouvert) ne sort que vers les domaines de `VEILLE_DOMAINES_AUTORISES`, en `https` (`VEILLE_SCHEMAS_AUTORISES`), depuis les pages de départ de `VEILLE_SEEDS`.

## Règles de collecte

- Agent déclaré : `MirAI-veille/1.0 (ministere de l'Interieur ; contact: <VEILLE_CONTACT>)`, sans accent (en-tête HTTP).
- `robots.txt` lu et respecté pour chaque hôte (`urllib.robotparser`) ; une interdiction vaut refus sans requête.
- En-têtes de cache honorés (`If-None-Match` / `ETag`, `304`) ; aucune page n'est rechargée inutilement.
- Au plus `MAX_PAGES` (5) pages par collecte, budget réparti entre les pages de départ ; seuls les liens du même hôte dont le libellé ou l'adresse porte un mot du sujet sont suivis ; une page suivie qui ne porte pas le sujet (titre, extrait) est écartée. Les mots vides (« des », « les », « pour »…) ne retiennent rien ; accents et majuscules sont neutralisés.
- Ce qui est conservé d'une page : titre, adresse, date de publication si déclarée, auteur s'il est fourni par une source officielle, extrait de 300 caractères au plus (balises `head`, `script`, `style`, `nav` retirées). Jamais le texte intégral, jamais de rendu JavaScript, aucun contournement d'un mur d'accès.
- Hors sources officielles, un champ reconnu nominatif (auteur) n'est pas conservé.
- Les adresses consultées sont rendues avec le résultat et journalisées avec l'exécution.

## Domaines retenus en preview (2026-10-11)

| Domaine | Réponse à l'agent déclaré | Retenu |
|---|---|---|
| `www.service-public.gouv.fr` (et `www.service-public.fr`, qui y redirige) | 200 | oui, page de départ `/particuliers/actualites` |
| `cyber.gouv.fr` | 200 | oui, page de départ `/actualites` |
| `www.cnil.fr`, `www.conseil-etat.fr`, `www.assemblee-nationale.fr`, `www.senat.fr` | 200 | oui |
| `www.vie-publique.fr` | 200, page de 232 octets (défi JavaScript) | listé, inexploitable sans rendu |
| `www.interieur.gouv.fr`, `www.legifrance.gouv.fr`, `www.info.gouv.fr` (`www.gouvernement.fr` y redirige) | **403** | listés, fermés à l'agent : question ouverte (inscription de l'agent, flux RSS ou API) |

Légifrance est consulté par la capacité `legifrance.rechercher` (serveur MCP Légifrance, compte technique PISTE), pas par la collecte web.
