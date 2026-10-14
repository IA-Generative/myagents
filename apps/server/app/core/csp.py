"""Content-Security-Policy de la SPA servie par FastAPI."""

from urllib.parse import urlsplit

from app.core.config import Settings

# vue-dsfr charge ses icônes `ri-*` depuis l'API Iconify tant qu'elles ne sont pas embarquées.
ICONIFY_HOSTS = (
    "https://api.iconify.design",
    "https://api.simplesvg.com",
    "https://api.unisvg.com",
)

# Swagger UI (dev) charge ses scripts depuis un CDN : pas de CSP sur ces chemins.
CSP_EXEMPT_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


def _origin(url: str) -> str | None:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None


def build_csp(settings: Settings) -> str:
    connect = ["'self'", *ICONIFY_HOSTS, *settings.csp_extra_connect_src]
    # oidc-client-ts appelle l'IdP (discovery, token, userinfo) depuis le navigateur.
    if settings.oidc_issuer and (issuer := _origin(settings.oidc_issuer)):
        connect.append(issuer)
    directives = {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        # Les composants Vue/DSFR posent des attributs style inline.
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:"],
        "font-src": ["'self'", "data:"],
        "connect-src": connect,
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
    }
    return "; ".join(
        f"{name} {' '.join(values)}" for name, values in directives.items()
    )
