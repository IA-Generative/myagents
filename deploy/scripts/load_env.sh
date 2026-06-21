#!/usr/bin/env bash
# Chargement de fichier .env compatible avec owuicore-main.
# Règle clé : `load_dotenv_preserve_existing` n'écrase JAMAIS une variable
# déjà exportée dans l'environnement shell. Ça permet :
#   - de superposer plusieurs .env (le premier chargé gagne)
#   - d'overrider via l'environnement CI sans modifier les fichiers
#
# Fonction copiée depuis owuicore-main/scripts/load_env.sh pour que
# owuiapps-agents reste déployable même si le socle n'est pas cloné
# à côté.

load_dotenv_preserve_existing() {
  local env_file="${1:-.env}"
  local line key value

  if [[ ! -f "$env_file" ]]; then
    return 0
  fi

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue

    line="${line#"${line%%[![:space:]]*}"}"
    if [[ "$line" =~ ^export[[:space:]]+ ]]; then
      line="${line#export }"
    fi

    key="${line%%=*}"
    value="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"

    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      continue
    fi

    if [[ -n "${!key+x}" ]]; then
      export "$key"
      continue
    fi

    export "${key}=${value}"
  done < "$env_file"
}
