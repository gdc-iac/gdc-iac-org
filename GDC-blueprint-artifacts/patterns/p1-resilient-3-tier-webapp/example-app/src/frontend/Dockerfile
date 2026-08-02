FROM nginx:alpine

# Create a non-root user (nginx user already exists in alpine image, usually uid 101)
# We just need to ensure permissions are correct for pid and cache
RUN mkdir -p /var/cache/nginx /var/run /var/log/nginx /tmp/nginx && \
    chmod -R 777 /var/cache/nginx /var/run /var/log/nginx /tmp/nginx && \
    chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx /etc/nginx/conf.d /tmp/nginx && \
    sed -i 's|/var/run/nginx.pid|/tmp/nginx/nginx.pid|' /etc/nginx/nginx.conf || echo "pid /tmp/nginx/nginx.pid;" >> /etc/nginx/nginx.conf

COPY index.html /usr/share/nginx/html/index.html
COPY nginx.conf /etc/nginx/templates/default.conf.template

USER nginx
EXPOSE 8080
