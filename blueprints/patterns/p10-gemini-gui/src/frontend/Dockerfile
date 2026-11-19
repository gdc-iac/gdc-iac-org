FROM node:22-alpine AS build

WORKDIR /app
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN mkdir -p /var/cache/nginx /var/run /var/log/nginx /tmp/nginx && \
    chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx /tmp/nginx /etc/nginx/conf.d /usr/share/nginx/html && \
    chmod -R 755 /var/cache/nginx /var/run /var/log/nginx /tmp/nginx && \
    sed -i 's|pid\s*.*;|pid /tmp/nginx/nginx.pid;|' /etc/nginx/nginx.conf
USER nginx
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
