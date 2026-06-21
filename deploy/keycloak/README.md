# Keycloak — client MirAI Agent Builder

Le socle `owuicore-main` héberge un Keycloak avec le realm `openwebui` exposé sur
`https://mysso.fake-domain.name`. MirAI Agent Builder réutilise ce realm en
ajoutant un client OIDC confidentiel dédié.

## Import manuel

1. Connexion à l'admin Keycloak : `https://mysso.fake-domain.name/admin`
2. Realm `openwebui` → Clients → **Create client** → Import JSON
3. Sélectionner [client-miraiku-agents.json](client-miraiku-agents.json)
4. Dans l'onglet **Credentials**, générer un secret client (**Regenerate**)
5. Copier le secret dans `.env` (`KEYCLOAK_CLIENT_SECRET=...`)
6. Mettre à jour le Secret K8s : `./deploy/prepare-secrets.sh`

## Intégration au realm.json du socle (recommandé)

Plus reproductible : ajouter le bloc `client-miraiku-agents.json` au tableau
`clients` de [owuicore-main/keycloak/realm-openwebui.k8s.json](../../../owuicore-main/keycloak/realm-openwebui.k8s.json)
et relancer `./deploy/deploy-k8s.sh` du socle pour recharger le ConfigMap
`keycloak-realm`. Ça permet de provisionner le client à la création du cluster
plutôt que manuellement.
