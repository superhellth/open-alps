FROM node:24-alpine AS build
WORKDIR /open-alps
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
RUN npm run build

FROM caddy:2-alpine
RUN apk add --no-cache libcap \
 && setcap -r /usr/bin/caddy \
 && apk del libcap \
 && addgroup -S -g 10001 caddy \
 && adduser -S -u 10001 -G caddy -H caddy \
 && mkdir -p /data /config \
 && chown -R 10001:10001 /data /config
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /open-alps/dist /srv
USER 10001:10001
EXPOSE 8080