# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM nginx:1.27-alpine

ENV API_UPSTREAM=http://logic-svc:8080

COPY index.html /usr/share/nginx/html/index.html
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Ensure least-privilege permissions for non-root nginx user (UID/GID 101)
# Use /tmp/nginx.pid directly so an emptyDir mount on /tmp never hides a subdirectory
RUN mkdir -p /var/cache/nginx /var/run /var/log/nginx /etc/nginx/templates && \
    chown -R 101:101 /var/cache/nginx /var/run /var/log/nginx /etc/nginx/conf.d /etc/nginx/templates /usr/share/nginx/html && \
    chmod -R 755 /var/cache/nginx /var/run /var/log/nginx /etc/nginx/conf.d /etc/nginx/templates /usr/share/nginx/html && \
    sed -i 's|pid\s*.*;|pid /tmp/nginx.pid;|' /etc/nginx/nginx.conf

USER 101:101
EXPOSE 8080
