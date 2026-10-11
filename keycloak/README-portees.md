# Portées Keycloak du contrat de capacités (ADR « Mes agents : capacités gouvernées », §4.7)

`mesagents-portees.client-scopes.json` contient cinq portées client (*client scopes*) à importer
dans le realm des consommateurs. Elles remplacent la portée `mesagents-agents` du contrat V1.

| Portée | Mappers | À affecter (en OPTIONNEL) aux clients… |
|---|---|---|
| `mesagents:read` | audience `mesagents` + `groups` en chemins complets | de toute surface consommatrice (socle, extensions, Mon portail) |
| `mesagents:act` | audience `mesagents` | des surfaces qui savent afficher une confirmation (Mon portail, extensions bureautiques) |
| `mesagents:author` | audience `mesagents` | des surfaces de création (Mes agents web, Mon portail, extension Thunderbird) |
| `mesagents:review` | audience `mesagents` | des surfaces de revue (Mes agents web) — et le rôle de realm `mesagents-reviewer` aux personnes |
| `mesagents:delegate` | audience `mesagents` | **aucun** client interactif ; hors V2, refusée par Mes agents |

## Import (kcadm, un realm à la fois)

```sh
for i in 0 1 2 3 4; do
  jq ".[$i]" keycloak/mesagents-portees.client-scopes.json \
    | kcadm.sh create client-scopes -r <realm> -f -
done
# puis, pour chaque client :
kcadm.sh update clients/<id-du-client>/optional-client-scopes/<id-de-la-portee> -r <realm>
# et le rôle des relecteurs :
kcadm.sh create roles -r <realm> -s name=mesagents-reviewer
```

Variante pour le realm `preview` du Keycloak intermédiaire des previews : ce realm n'a pas de
groupes locaux, le mapper `groups` lit l'attribut `groupes_amont` (voir le script
`scripts/sso-preview-portees-mesagents-v2.sh` du dépôt de déploiement).

## Nommage

Le nom contient « : » (`mesagents:read`). Si un Keycloak refusait ce caractère, nommer
`mesagents-read`, … : le service rabat ces alias sur la forme canonique
(`app/core/portees.py`, variable `MESAGENTS_PORTEES_ALIAS` pour d'autres alias).

## Ce qu'un consommateur demande

`scope=openid profile email mesagents:read [mesagents:act] [mesagents:author]` à l'autorisation.
Le jeton d'accès porte alors `aud: mesagents`, `azp: <client>`, `scope: …`, `groups: [/g/…]`.
Un rafraîchissement n'ajoute jamais une portée : changer les portées demandées impose une
nouvelle connexion.
