# Open Terminal + assets DSFR (Marianne, couleurs, bloc-marque) et CLI `dsfr-doc`.
ARG OPEN_TERMINAL_IMAGE_TAG=latest
FROM ghcr.io/open-webui/open-terminal:${OPEN_TERMINAL_IMAGE_TAG}

USER root

# --ignore-scripts : le preinstall du paquet exige un projet DSFR initialisé.
RUN mkdir -p /opt/dsfr && cd /opt/dsfr \
    && npm init -y >/dev/null \
    && npm install --ignore-scripts --omit=dev @gouvfr/dsfr@1.15.3 \
    && rm -rf /root/.npm

COPY dsfr/ /opt/dsfr-doc/
RUN chmod 0755 /opt/dsfr-doc/dsfr-doc && ln -s /opt/dsfr-doc/dsfr-doc /usr/local/bin/dsfr-doc

# Permet `import dsfr_office` depuis les scripts du modèle.
ENV PYTHONPATH=/opt/dsfr-doc

USER user
