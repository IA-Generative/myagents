# Image de dev (serveur Vite, hot reload) — l'image de production est le Dockerfile racine.
ARG BUN_VERSION=1.4.2
FROM oven/bun:${BUN_VERSION}-alpine

WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

COPY . .

EXPOSE 5173
CMD ["bun", "run", "dev", "--", "--host", "0.0.0.0"]
