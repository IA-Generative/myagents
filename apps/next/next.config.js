/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // react-dsfr requires this for server components compatibility
  // (Next 15 : renommé depuis experimental.serverComponentsExternalPackages)
  serverExternalPackages: ['@codegouvfr/react-dsfr'],
  // On sert l'app derrière un ingress nginx qui gère déjà la compression/TLS
  poweredByHeader: false,

  // En-têtes de sécurité appliqués à toutes les réponses. La CSP est posée en
  // Report-Only pour ne pas casser les styles/scripts inline du DSFR : à
  // observer dans les logs navigateur avant de basculer en CSP bloquante.
  async headers() {
    const csp = [
      "default-src 'self'",
      "base-uri 'self'",
      "object-src 'none'",
      "frame-ancestors 'none'",
      "img-src 'self' data:",
      "style-src 'self' 'unsafe-inline'",
      "script-src 'self' 'unsafe-inline'",
    ].join('; ');
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=()',
          },
          {
            key: 'Strict-Transport-Security',
            value: 'max-age=63072000; includeSubDomains; preload',
          },
          { key: 'Content-Security-Policy-Report-Only', value: csp },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
