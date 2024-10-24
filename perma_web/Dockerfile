FROM registry.lil.tools/library/debian:11.3
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_SRC=/usr/local/src \
    OPENSSL_CONF=/etc/ssl
RUN mkdir -p /perma/perma_web
WORKDIR /perma/perma_web

# Get build dependencies and packages required by the app
RUN apt-get update \
    && apt-get install -y wget \
    && apt-get install -y curl \
    && apt-get install -y bzip2 \
    && apt-get install -y gnupg \
    && apt-get install -y python3-pip \
    && apt-get install -y python3-dev \
    && apt-get install -y python-is-python3 \
    && apt-get install -y virtualenv \
    && apt-get install -y git \
    \
    && apt-get install -y postgresql-client \
    && apt-get install -y libpq-dev \
    && apt-get install -y xvfb \
    && apt-get install -y libffi-dev \
    && apt-get install -y libjpeg62-turbo-dev \
    && apt-get install -y libfontconfig1 \
    && apt-get install -y imagemagick \
    && apt-get install -y libmagickwand-dev

# Install commonly used web fonts for better screen shots.
RUN echo "deb http://deb.debian.org/debian bullseye main contrib" > /etc/apt/sources.list \
    && echo "deb https://deb.debian.org/debian-security bullseye-security main contrib" >> /etc/apt/sources.list \
    && echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections \
    && apt-get update \
    && apt-get install -y ttf-mscorefonts-installer \
    && apt-get install -y fonts-roboto

# Install a cert for use by warcprox
COPY services/warcprox/perma-warcprox-ca.pem /perma/perma_web
RUN apt-get update && apt-get install -y libnss3-tools \
    && mkdir -p $HOME/.pki/nssdb \
    && certutil -d $HOME/.pki/nssdb -N --empty-password \
    && certutil -d sql:$HOME/.pki/nssdb -A -t "C,," -n 'warcprox CA cert' -i perma-warcprox-ca.pem

# Install Tor, for optional use as a proxy
RUN apt-get update && apt-get install -y tor

# pin node version -- see https://github.com/nodesource/distributions/issues/33
ARG BUILDARCH
ENV BUILDARCH=${BUILDARCH:-amd64}
RUN curl -o nodejs.deb https://deb.nodesource.com/node_14.x/pool/main/n/nodejs/nodejs_14.19.0-deb-1nodesource1_${BUILDARCH}.deb \
    && dpkg -i ./nodejs.deb \
    && rm nodejs.deb

# npm
COPY perma_web/package.json /perma/perma_web
COPY perma_web/npm-shrinkwrap.json /perma/perma_web
RUN npm install \
    && rm package.json \
    && rm npm-shrinkwrap.json

# python requirements
COPY perma_web/requirements.txt /perma/perma_web
RUN pip install pip==22.0.4 \
    && pip install -r /perma/perma_web/requirements.txt \
    && rm /perma/perma_web/requirements.txt

# Install Chromium and driver
ARG chrome-layer-cache-buster
RUN apt-get update && apt-get install -y chromium chromium-driver chromium-l10n chromium-sandbox

# dev personalizations / try installing packages without rebuilding everything
RUN apt-get update && apt-get install -y nano
