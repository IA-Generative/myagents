# MirAI Agent Builder — Dockerfile multi-stage (Next.js 14 standalone)
# Registre cible : rg.fr-par.scw.cloud/${NAMESPACE}/miraiku-agents:${IMAGE_TAG}

# ---------- Stage 1 : deps ----------
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat openssl
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ---------- Stage 2 : builder ----------
FROM node:20-alpine AS builder
RUN apk add --no-cache openssl
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Copie les assets DSFR dans public/ pour qu'ils soient servis statiquement
# par Next.js, sans passer par le css-loader webpack qui explose sa pile
# sur l'arborescence d'imports de main.css.
RUN mkdir -p public/dsfr && cp -r node_modules/@codegouvfr/react-dsfr/dsfr/* public/dsfr/
# Prisma client a besoin du schema avant le build Next
RUN npx prisma generate
ENV NEXT_TELEMETRY_DISABLED=1
# Skip runtime env validation during build — secrets sont injectés au démarrage
# du conteneur, pas au build. src/lib/env.ts retourne des placeholders quand
# SKIP_ENV_VALIDATION=1 pour que Next.js puisse faire le static analysis des
# routes API sans qu'authOptions/KeycloakProvider ne plante.
ENV SKIP_ENV_VALIDATION=1
RUN npm run build

# ---------- Stage 3 : runner ----------
FROM node:20-alpine AS runner
RUN apk add --no-cache openssl
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
# Docker injecte HOSTNAME=<container id> par défaut ; le serveur Next.js
# standalone s'y bind alors littéralement, ce qui rend localhost injoignable
# (healthcheck en ECONNREFUSED). On force le bind sur toutes les interfaces.
ENV HOSTNAME=0.0.0.0

# User non-root aligné avec le securityContext K8s (runAsUser: 1001)
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
# Le client Prisma et le schéma sont requis au runtime pour les migrations
COPY --from=builder --chown=nextjs:nodejs /app/prisma ./prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/@prisma/client ./node_modules/@prisma/client

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD node -e "fetch('http://localhost:3000/api/health').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
