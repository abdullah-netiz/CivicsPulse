FROM node:22-alpine AS build
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
# Probe the IPv4 loopback explicitly. Inside this image /etc/hosts maps
# `localhost` to `::1` (IPv6) first, but nginx listens on IPv4 0.0.0.0:80
# only, so `http://localhost/` is refused and the container reports
# unhealthy even though the server is fine. 127.0.0.1 removes the ambiguity.
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1/ || exit 1
