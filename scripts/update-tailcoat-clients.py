"""Run once on decanid_default with Tailcoat .env mounted read-only at /run/tailcoat.env.
Updates public OAuth URLs without resetting the realm, clients, users, or passwords.
"""
import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode

env=dict(line.split('=',1) for line in Path('/run/tailcoat.env').read_text().splitlines() if line and not line.startswith('#'))
base='http://identity:8080'
body=urlencode({'client_id':'admin-cli','grant_type':'password','username':env.get('ADMIN_USERNAME','admin'),'password':env['ADMIN_PASSWORD']}).encode()
with urlopen(Request(base+'/realms/master/protocol/openid-connect/token',data=body),timeout=20) as response:
    token=json.load(response)['access_token']
headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
with urlopen(Request(base+'/admin/realms/decanid/clients',headers=headers),timeout=20) as response:
    clients=json.load(response)
origins={'decanid-portal':'https://tailcoat.decaneva.cloud','ti-turn-tracker':'https://imperium.decaneva.cloud','mtg':'https://mtg.decaneva.cloud'}
for client in clients:
    if client['clientId'] not in origins: continue
    origin=origins[client['clientId']]
    client.update(rootUrl=origin,baseUrl='/',redirectUris=[origin+'/',origin+'/auth/callback'],webOrigins=[origin])
    client.setdefault('attributes',{})['post.logout.redirect.uris']=origin+'/'
    request=Request(base+'/admin/realms/decanid/clients/'+client['id'],headers=headers,data=json.dumps(client).encode(),method='PUT')
    with urlopen(request,timeout=20) as response:
        print('Updated OAuth URLs:',client['clientId'],response.status)
