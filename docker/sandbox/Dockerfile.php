# PHP sandbox: composer baked so install_cmds can `composer install`.
FROM php:8.3-cli-bookworm
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer
RUN apt-get update \
  && apt-get install -y --no-install-recommends git unzip ca-certificates libicu-dev libzip-dev \
  && docker-php-ext-install mbstring xml intl zip pdo_sqlite \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /work
