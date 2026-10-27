FROM nginx:1.27-alpine

# Create a non-root user (nginx user already exists in alpine image, usually uid 101)
# Ensure least-privilege permissions for pid and cache directories
RUN mkdir -p /var/cache/nginx /var/run /var/log/nginx /tmp/nginx && \
    chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx /etc/nginx/conf.d /tmp/nginx && \
    chmod -R 755 /var/cache/nginx /var/run /var/log/nginx /tmp/nginx && \
    sed -i 's|/var/run/nginx.pid|/tmp/nginx/nginx.pid|' /etc/nginx/nginx.conf || echo "pid /tmp/nginx/nginx.pid;" >> /etc/nginx/nginx.conf

COPY index.html /usr/share/nginx/html/index.html
COPY nginx.conf /etc/nginx/templates/default.conf.template

USER nginx
EXPOSE 8080
