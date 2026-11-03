FROM nginx:1.28-alpine
RUN apk add --no-cache python3 certbot openssl curl
COPY scripts /opt/proxy
COPY config /opt/config
RUN rm -f /etc/nginx/conf.d/default.conf
ENTRYPOINT ["python3", "/opt/proxy/runtime.py"]
