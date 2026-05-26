FROM node:20-alpine

WORKDIR /app

ENV PROXY_HOST=188.136.214.220 \
    PROXY_PORT=10810 \
    PROXY_USER=ehsan \
    PROXY_PASS=Daryayeabi9%2F9

#RUN npm config --global set registry https://mirror.abrha.net/repository/npm/

COPY frontend/package*.json ./

RUN npm config set registry https://registry.npmjs.org/ \
    && npm config delete proxy || true \
    && npm config delete https-proxy || true

RUN npm config set registry https://registry.npmjs.org/ \
    && npm config set proxy "socks5h://${PROXY_USER}:${PROXY_PASS}@${PROXY_HOST}:${PROXY_PORT}" \
    && npm config set https-proxy "socks5h://${PROXY_USER}:${PROXY_PASS}@${PROXY_HOST}:${PROXY_PORT}" \
    && npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm install --include=dev

#RUN npm install

COPY frontend .

#CMD ["npm", "run", "dev"]
RUN npm run build

#RUN npm config delete proxy || true \
#    && npm config delete https-proxy || true

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1

EXPOSE 3000

CMD ["npm", "start"]
