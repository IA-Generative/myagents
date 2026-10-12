#!/usr/bin/env python3
"""Obtient un jeton d'accès d'une PERSONNE RÉELLE sur le realm `preview` du Keycloak intermédiaire
des previews, pour rejouer la suite de conformité contre une preview (tests/conformite, JETONS_DIR).

Le realm n'a pas de compte local et refuse le mot de passe direct : le script mène lui-même un
flux « code d'autorisation + PKCE » dans un navigateur (Playwright), avec le compte d'essai du SSO
amont, intercepte l'adresse de retour (l'application ne voit jamais le code) et échange le code
sans secret (client public). Le jeton est écrit dans un fichier (mode 0600), jamais affiché.

    scripts/jeton-preview.py --redirect https://myagents-pr-54.beta-preview.numerique-interieur.com/api/auth/callback \\
        --client mirai-preview --compte in --portees "mesagents:read mesagents:act mesagents:author" \\
        --sortie private/jetons/mirai-preview-alice.json
    scripts/jeton-preview.py --rafraichir private/jetons/mirai-preview-alice.json

Identifiants : variables d'environnement KC_TEST_IN_USERNAME/KC_TEST_IN_PASSWORD (compte « in »),
KC_TEST_OUT_* (« out »), KC_PREVIEW_ESSAI_* (« essai »), ou lus dans --credentials <fichier .env>.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ISSUER = "https://sso.beta-preview.numerique-interieur.com/realms/preview"
AMONT = {"in": "sso.mirai.interieur.gouv.fr", "out": "sso.mirai.interieur.gouv.fr", "essai": "mysso.fake-domain.name"}
VARIABLES = {
    "in": ("KC_TEST_IN_USERNAME", "KC_TEST_IN_PASSWORD"),
    "out": ("KC_TEST_OUT_USERNAME", "KC_TEST_OUT_PASSWORD"),
    "essai": ("KC_PREVIEW_ESSAI_USERNAME", "KC_PREVIEW_ESSAI_PASSWORD"),
}


def _b64url(donnees: bytes) -> str:
    return base64.urlsafe_b64encode(donnees).rstrip(b"=").decode()


def _charge(jwt: str) -> dict:
    partie = jwt.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(partie + "=" * (-len(partie) % 4)))


def _identifiants(compte: str, credentials: str | None) -> tuple[str, str]:
    cle_u, cle_m = VARIABLES[compte]
    valeurs = dict(os.environ)
    if credentials:
        for ligne in Path(credentials).read_text().splitlines():
            if "=" in ligne and not ligne.lstrip().startswith("#"):
                k, _, v = ligne.partition("=")
                valeurs.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    u, m = valeurs.get(cle_u, ""), valeurs.get(cle_m, "")
    if not u or not m or u.startswith("CHANGE_ME"):
        sys.exit(f"⛔ identifiants absents : {cle_u} / {cle_m}")
    return u, m


def _echange(token_endpoint: str, data: dict) -> dict:
    req = urllib.request.Request(token_endpoint, data=urllib.parse.urlencode(data).encode(), method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _ecrire(sortie: Path, contenu: dict) -> None:
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(contenu))
    os.chmod(sortie, 0o600)


def rafraichir(fichier: Path) -> int:
    contenu = json.loads(fichier.read_text())
    reponse = _echange(contenu["token_endpoint"], {"grant_type": "refresh_token", "client_id": contenu["client_id"], "refresh_token": contenu["refresh_token"]})
    contenu.update(reponse)
    _ecrire(fichier, contenu)
    print(f"✅ jeton rafraîchi : {fichier} (exp dans {_charge(contenu['access_token'])['exp'] - int(time.time())} s)")
    return 0


def obtenir(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    user, mdp = _identifiants(args.compte, args.credentials)
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state = secrets.token_urlsafe(16)
    portees = " ".join(dict.fromkeys(["openid", "profile", "email", *args.portees.split()]))
    auth_url = f"{ISSUER}/protocol/openid-connect/auth?" + urllib.parse.urlencode({
        "client_id": args.client, "response_type": "code", "scope": portees, "redirect_uri": args.redirect,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })
    token_endpoint = f"{ISSUER}/protocol/openid-connect/token"
    retour: dict[str, str] = {}

    with sync_playwright() as p:
        nav = p.chromium.launch()
        page = nav.new_context().new_page()

        hotes: list[str] = []

        def requete(r):
            if not (r.is_navigation_request() and r.frame == page.main_frame):
                return
            parts = urllib.parse.urlsplit(r.url)
            hotes.append(parts.netloc + parts.path[:40])
            if r.url.startswith(args.redirect):
                # Le code est lu sur la requête de retour ; la page servie derrière importe peu
                # (adresse sous l'hôte de la preview, enregistrée par l'automate en `/*`).
                retour.update(dict(urllib.parse.parse_qsl(parts.query)))

        page.on("request", requete)
        page.goto(auth_url, wait_until="domcontentloaded", timeout=45_000)
        try:
            page.wait_for_url(lambda u: urllib.parse.urlsplit(u).netloc == AMONT[args.compte], timeout=30_000)
        except Exception:  # noqa: BLE001
            print(f"⚠️  pas d'arrivée chez l'amont ({AMONT[args.compte]}) : {page.url[:120]}")
            nav.close()
            return 2
        page.locator("input[name=username]").fill(user)
        page.locator("input[name=password]").fill(mdp)
        page.locator("#kc-login, button[type=submit]").first.click()
        for _ in range(60):
            if "code" in retour:
                break
            page.wait_for_timeout(500)
        derniere = page.url
        try:
            extrait = " ".join(page.locator("body").inner_text()[:300].split())
        except Exception:  # noqa: BLE001
            extrait = ""
        nav.close()
    if "code" not in retour:
        print(f"⚠️  aucun code reçu sur {args.redirect} (state attendu {state})")
        print(f"   hôtes traversés : {' → '.join(dict.fromkeys(hotes))}")
        print(f"   dernière page : {derniere[:160]} « {extrait} »")
        return 1
    if retour.get("state") != state:
        print("⚠️  state inattendu")
        return 1
    reponse = _echange(token_endpoint, {
        "grant_type": "authorization_code", "client_id": args.client, "code": retour["code"],
        "redirect_uri": args.redirect, "code_verifier": verifier,
    })
    charge = _charge(reponse["access_token"])
    aud = charge.get("aud")
    aud = aud if isinstance(aud, list) else [aud]
    print(f"✅ jeton obtenu : iss={charge.get('iss')} azp={charge.get('azp')} aud={aud} scope=« {charge.get('scope')} » groups={charge.get('groups')}")
    if "mesagents" not in aud:
        print("⚠️  l'audience « mesagents » manque : les portées mesagents:* ne sont pas attachées au client, ou non demandées")
    sortie = Path(args.sortie)
    _ecrire(sortie, {**reponse, "client_id": args.client, "token_endpoint": token_endpoint, "compte": args.compte})
    print(f"   écrit dans {sortie} (0600)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", default="mirai-preview")
    ap.add_argument("--compte", choices=list(VARIABLES), default="in")
    ap.add_argument("--portees", default="mesagents:read mesagents:act mesagents:author")
    ap.add_argument("--redirect", help="adresse de retour sous un hôte enregistré sur le client, ex. https://myagents-pr-54.beta-preview.numerique-interieur.com/.well-known/jeton-preview (jamais le callback de l'application : il consommerait le code)")
    ap.add_argument("--sortie", default=None, help="fichier du jeton (défaut : private/jetons/<client>-<compte>.json)")
    ap.add_argument("--credentials", default=None, help="fichier .env des identifiants d'essai")
    ap.add_argument("--rafraichir", default=None, help="rafraîchit le jeton de ce fichier et sort")
    args = ap.parse_args()
    if args.rafraichir:
        return rafraichir(Path(args.rafraichir))
    if not args.redirect:
        ap.error("--redirect est requis")
    if not args.sortie:
        args.sortie = f"private/jetons/{args.client}-{args.compte}.json"
    return obtenir(args)


if __name__ == "__main__":
    raise SystemExit(main())
