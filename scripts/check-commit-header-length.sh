#!/usr/bin/env bash
# Vérifie que la première ligne du message de commit (en-tête) ne dépasse pas
# la limite imposée par commitlint dans la CI (header-max-length = 100).
#
# Ce hook complète conventional-pre-commit, qui valide le format Conventional
# Commits mais PAS la longueur de l'en-tête.
#
# Règle alignée sur dnum-mi/fabnum-cicd/lint-commits.yml (MAX_SUBJECT_LENGTH=100).
set -euo pipefail

MAX_LENGTH=100

# pre-commit passe le fichier de message de commit en premier argument.
COMMIT_MSG_FILE="${1:-}"

if [[ -z "$COMMIT_MSG_FILE" ]]; then
  echo "commit-header-length: aucun fichier de message fourni" >&2
  exit 1
fi

# Lire uniquement la première ligne (l'en-tête), en retirant les commentaires
# que git ajoute (lignes commençant par '#').
HEADER=$(sed '/^#/d; /^$/d' "$COMMIT_MSG_FILE" | head -1)

# Les commits de merge et les fixup!/squash! sont exemptés (aligné sur
# conventional-pre-commit qui les laisse passer en mode non-strict).
if [[ "$HEADER" =~ ^Merge\  ]] || [[ "$HEADER" =~ ^(fixup|squash)!\  ]]; then
  exit 0
fi

HEADER_LEN=${#HEADER}

if (( HEADER_LEN > MAX_LENGTH )); then
  echo "❌ En-tête de commit trop long : ${HEADER_LEN} caractères (max ${MAX_LENGTH})." >&2
  echo "" >&2
  echo "   ${HEADER}" >&2
  echo "" >&2
  echo "   Raccourcissez le message. La CI (commitlint, header-max-length) rejette" >&2
  echo "   tout en-tête dépassant ${MAX_LENGTH} caractères." >&2
  exit 1
fi
