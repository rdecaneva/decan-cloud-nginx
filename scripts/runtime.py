"""One certificate writer and nginx replicas with validated automatic reloads."""
import hashlib,json,os,re,signal,subprocess,sys,time
from pathlib import Path

def routes():
    items=json.loads(Path('/opt/config/routes.json').read_text())
    seen=set()
    for x in items:
        for host in [x['domain'],x['certificate'],*x.get('certificate_domains',[])]:
            if not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*',host): raise ValueError('Invalid hostname')
        if x['domain'] in seen: raise ValueError('Duplicate hostname')
        seen.add(x['domain'])
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*:[0-9]{1,5}',x['upstream']): raise ValueError('Invalid upstream')
        if not re.fullmatch(r'[0-9]+[mk]?',x['body_size']): raise ValueError('Invalid upload limit')
    return items

def certdir(x):
    p=Path('/etc/letsencrypt/live')/x['certificate']
    return p if (p/'fullchain.pem').is_file() and (p/'privkey.pem').is_file() else Path('/bootstrap')/x['certificate']

def render(items):
    result='''map $http_upgrade $connection_upgrade { default upgrade; '' close; }
resolver 127.0.0.11 valid=5s ipv6=off;
resolver_timeout 3s;
server_tokens off;
# Traffic ports are unpublished and reachable only by the edge network.
set_real_ip_from 0.0.0.0/0;
real_ip_header proxy_protocol;
log_format edge '$remote_addr $host "$request" $status $body_bytes_sent';
access_log /dev/stdout edge;
server {
 listen 8080;
 location = /healthz { access_log off; return 200 'ok'; }
 location / { return 404; }
}
server {
 listen 80 proxy_protocol default_server;
 server_name _;
 location /.well-known/acme-challenge/ { root /var/www/certbot; }
 location / { return 444; }
}
server { listen 443 ssl proxy_protocol default_server; ssl_reject_handshake on; }
'''
    for x in items:
        d,u,b=x['domain'],x['upstream'],x['body_size']; c=certdir(x)
        result+=f'''
server {{
 listen 80 proxy_protocol;
 server_name {d};
 location /.well-known/acme-challenge/ {{ root /var/www/certbot; }}
 location / {{ return 308 https://{d}$request_uri; }}
}}
server {{
 listen 443 ssl proxy_protocol;
 http2 on;
 server_name {d};
 ssl_certificate {c}/fullchain.pem;
 ssl_certificate_key {c}/privkey.pem;
 ssl_protocols TLSv1.2 TLSv1.3;
 ssl_session_cache shared:SSL:10m;
 ssl_session_tickets off;
 client_max_body_size {b};
 location / {{
  set $backend http://{u};
  proxy_pass $backend;
  proxy_http_version 1.1;
  proxy_set_header Host $http_host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $remote_addr;
  proxy_set_header X-Forwarded-Proto https;
  proxy_set_header X-Forwarded-Port 443;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection $connection_upgrade;
  proxy_connect_timeout 5s;
  proxy_read_timeout 3600s;
  proxy_send_timeout 3600s;
  proxy_buffering off;
 }}
}}
'''
    return result

def fingerprint(items):
    h=hashlib.sha256(render(items).encode())
    for x in items:
        for name in ['fullchain.pem','privkey.pem']: h.update((certdir(x)/name).read_bytes())
    return h.hexdigest()

def proxy():
    target=Path('/etc/nginx/conf.d/services.conf'); items=routes()
    target.write_text(render(items)); subprocess.run(['nginx','-t'],check=True)
    child=subprocess.Popen(['nginx','-g','daemon off;'])
    def stop(*_):
        child.send_signal(signal.SIGQUIT)
        try: child.wait(timeout=10)
        except subprocess.TimeoutExpired: child.terminate()
        sys.exit(0)
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    last=fingerprint(items)
    while child.poll() is None:
        time.sleep(10)
        try:
            items=routes(); current=fingerprint(items)
            if current!=last:
                old=target.read_text();target.write_text(render(items))
                if subprocess.run(['nginx','-t']).returncode==0:
                    child.send_signal(signal.SIGHUP);last=current
                    print('Reloaded configuration/certificates',flush=True)
                else: target.write_text(old)
        except Exception as e: print('Keeping current nginx configuration:',e,flush=True)
    sys.exit(child.returncode)

def certificates():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    for x in routes():
        p=Path('/bootstrap')/x['certificate'];p.mkdir(parents=True,exist_ok=True)
        if not (p/'fullchain.pem').is_file():
            domains=x.get('certificate_domains',[x['domain']])
            subprocess.run(['openssl','req','-x509','-nodes','-newkey','rsa:2048','-days','30',
                '-keyout',str(p/'privkey.pem'),'-out',str(p/'fullchain.pem'),'-subj','/CN='+domains[0],
                '-addext','subjectAltName='+','.join('DNS:'+d for d in domains)],
                check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            (p/'privkey.pem').chmod(0o600)
    Path('/var/www/certbot').mkdir(parents=True,exist_ok=True);Path('/bootstrap/ready').touch()
    time.sleep(20)
    staging=['--staging'] if os.getenv('LETSENCRYPT_STAGING')=='1' else []
    while True:
        seen=set()
        for x in routes():
            name=x['certificate']
            if name in seen: continue
            seen.add(name)
            if not (Path('/etc/letsencrypt/live')/name/'fullchain.pem').is_file():
                args=['certbot','certonly','--webroot','-w','/var/www/certbot','--cert-name',name,
                      '--email',os.environ['LETSENCRYPT_EMAIL'],'--agree-tos','--non-interactive',*staging]
                for d in x.get('certificate_domains',[x['domain']]): args.extend(['-d',d])
                print('Requesting certificate for '+name,flush=True)
                if subprocess.run(args).returncode: print('Certificate pending for '+name+'; retrying in one hour',flush=True)
        subprocess.run(['certbot','renew','--webroot','-w','/var/www/certbot','--non-interactive'])
        time.sleep(3600)

if __name__=='__main__':
    if sys.argv[1:]==['proxy']: proxy()
    elif sys.argv[1:]==['certificates']: certificates()
    else: raise SystemExit('Expected proxy or certificates')
