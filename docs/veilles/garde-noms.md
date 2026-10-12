# Veilles — garde des sujets : aucune personne physique

Règle (`app/veilles/garde_noms.py`, `REGLE`) : une veille ne peut pas cibler une personne physique. Un sujet reconnu comme le nom propre d'un individu (hors institution, fonction ou lieu) est refusé à la création et à la modification (`422 guard_rejected`, `details[]` lisible). Les noms cités dans un texte officiel restent tels que publiés dans les sources ; rien n'est extrait ni indexé par personne.

## Décision en deux temps

1. **Lexicale**, sans appel réseau (`decision_lexicale`, règles dans l'ordre) : premier mot institutionnel ou thématique (ministère, préfecture, conseil, tribunal, commune, code, loi, décret, réforme…) → admis ; un chiffre (loi 2026, article 12) → admis ; exactement deux mots en forme « Prénom Nom » (ou NOM en capitales) → refusé ; deux ou trois mots minuscules dont le dernier est une donnée personnelle (adresse, téléphone, domicile, famille, casier, salaire, santé) → refusé ; un mot institutionnel ailleurs dans le sujet → admis ; au moins deux mots capitalisés inconnus → ambigu, le juge décide ; sinon admis.
2. **Juge** (modèle de langue, invite `JUDGE_SUJET_SYSTEM`, réponse JSON `{"personne": true|false, "reason"}`) pour tout sujet que la décision lexicale ne tranche pas. Le juge est **fermé en cas de doute** : réponse illisible, indisponibilité ou erreur valent refus (`guard_rejected`, motif « juge indisponible »).

## Ce que la garde ne fait pas

- Elle ne lit pas les résultats : les sources collectées peuvent nommer des personnes (textes officiels) ; elles sont rendues telles quelles, bornées à 300 caractères, et ne sont pas indexées par personne.
- Elle ne remplace pas le contrôle des sources : la liste d'autorisation de domaines (`domaines-autorises.md`) et le compte technique de collecte (`service:veilles`, `azp mes-agents-cron`) en sont les autres bornes.

## Finalité affichée

Le texte de finalité (`GET /api/v2/schedules` → `finalite`) est rendu à la personne avant toute création ; il dit que la veille lui est personnelle, que la collecte est faite par le système sur des sources publiques déclarées, que les résultats sont conservés 90 jours puis purgés, et qu'aucune personne physique ne peut être suivie.
