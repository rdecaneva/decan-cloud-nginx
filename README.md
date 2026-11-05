# decan-cloud-nginx

Shared HTTPS ingress for Decan Cloud. HAProxy distributes connections across two nginx replicas; a separate Certbot container is the only certificate writer. nginx detects certificate/config changes every ten seconds, validates them, and reloads gracefully. Existing WebSocket connections continue during reloads.

| URL | Backend alias | Internal port |
| --- | --- | --- |
| https://mtg.decaneva.cloud | mtg-prod | 3000 |
| https://mtg-dev.decaneva.cloud | mtg-dev | 3000 |
| https://imperium.decaneva.cloud | imperium | 5173 |
| https://stats.decaneva.cloud | stats | 8000 |
| https://tailcoat.decaneva.cloud | tailcoat | 80 |
| https://sso.decaneva.cloud | authentik-sso | 9000 |

Only this stack owns host ports 80 and 443. HTTP redirects to the canonical HTTPS hostname. Unknown TLS names are rejected. All routes support WebSockets and preserve the original client IP using the PROXY protocol between HAProxy and nginx. Incoming forwarded headers are overwritten at nginx. The service network must contain trusted applications only; nginx traffic ports are never published directly.

## Run

1. Point each hostname at the public ingress IP and forward TCP 80/443 to this host. Remove stale AAAA records unless IPv6 also reaches ingress.
2. Copy `.env.example` to `.env` and set `LETSENCRYPT_EMAIL`.
3. Create `docker network create decan-cloud-services` once. Connect application services using external network aliases shown above; see each application's compose file. `scripts/connect-services.sh` attaches the currently deployed containers without recreating them.
4. Run `docker compose up -d --build`.
5. Run `python3 scripts/check-routes.py --trusted`.

Certbot uses HTTP-01 challenges served from a shared webroot by both nginx replicas. MTG production/dev share the original certificate; other services receive separate certificates. Missing certificates temporarily use a self-signed bootstrap certificate, **which browsers do not trust**. Issuance is retried hourly; renewal checks also run hourly. Once DNS is ready, `docker compose restart certificates` triggers a prompt retry. `docker compose logs certificates` shows issuance failures. Never treat bootstrap TLS as successful production certificate issuance.

Persistent named volumes: `letsencrypt` (accounts, renewal config, private keys), `bootstrap`, and `challenges`. Back up the Let's Encrypt volume securely. Do not delete volumes during upgrades, run multiple certificate writers against one volume, or commit keys/.env.

## Existing MTG migration

The original `mtg-tabletop_letsencrypt` volume was copied to this stack before cutover. The original volume and stopped `mtg-tabletop-web-1` container are retained for rollback. The MTG compose `web` service now requires profile `legacy-proxy`; normal app deployment no longer starts it. Avoid running that profile while shared ingress owns ports 80/443.

`scripts/cutover.sh` validates nginx, stops the previous proxy, starts shared ingress, and verifies the existing trusted MTG endpoint with retries while HAProxy health checks initialize. Failure restores the previous proxy. To roll back manually: `docker compose stop edge`, then `docker start mtg-tabletop-web-1`. This restores MTG routing only.

Tailcoat's external issuer is now `https://tailcoat.decaneva.cloud`. Its portal and existing OAuth client redirects were updated without replacing the realm or accounts. `scripts/update-tailcoat-clients.py` documents the one-time in-place migration; it reads credentials from a read-only file and never prints them.

## Availability and node failover

The two nginx replicas cover failure of either nginx container. HAProxy removes an unhealthy replica after two failed health checks and restores it after two successful checks. Existing connections to a failed container disconnect and clients must reconnect. The edge HAProxy, Docker host, application databases, and application containers currently remain single points of failure. This deployment **does not survive loss of the current host**.

For node HA, provide at least one additional host and a traffic failover mechanism. On a shared LAN, run this stack per host and put a floating IP in front of the two edge instances with Keepalived/VRRP (example in `ha/keepalived.conf.example`); the router must forward ports 80/443 to that floating IP. On separate networks use a health-checked external load balancer instead. DNS round robin alone does not supply reliable failover.

Before enabling node failover:

- Replace local Docker backend aliases on secondary nodes with reachable private backend addresses or replicated backend services. Docker bridge aliases are local to a host.
- Keep one certificate writer and distribute certificates atomically and securely to secondary nodes, or provide shared storage with correct permissions. HTTP-01 challenges must be reachable through every ingress node; share the challenge webroot or route challenges to the certificate writer. Ordinary Docker named volumes are local to a host.
- Replicate application state using each app's supported model; do not run multiple writers against copied SQLite files. Proxy HA cannot make a single-host database available after host loss.
- Test loss of each ingress node and the certificate writer before declaring node HA operational.

## Add a service

Add its hostname, unique service alias, certificate name, and body-size limit to `config/routes.json`. Join the app to `decan-cloud-services` with that alias. Add DNS, then restart `certificates` to create its bootstrap/certificate files before restarting nginx replicas. Verify using the checker and inspect the issuer/expiry of the public certificate. Keep dev and prod aliases and data volumes separate.

## Validation

`python3 scripts/check-routes.py --trusted` checks all HTTP redirects and HTTPS responses (Stats intentionally requires authentication; SSO can redirect to its login flow). `docker compose exec nginx-a nginx -t` and the same for nginx-b validate generated configuration. For a controlled replica-failure test stop nginx-a, run the checker while nginx-b serves traffic, and start nginx-a again. Repeat for nginx-b. Do not stop both replicas at once.

References: [nginx proxy configuration](https://nginx.org/en/docs/http/ngx_http_proxy_module.html), [Certbot operation](https://eff-certbot.readthedocs.io/en/stable/using.html), [Keepalived failover](https://www.keepalived.org/documentation/user-guide/quick-start/).
