"""Check canonical redirects and HTTPS upstreams; --trusted requires valid public certificates."""
import argparse,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--address',default='127.0.0.1');p.add_argument('--trusted',action='store_true');a=p.parse_args()
for item in json.loads((Path(__file__).resolve().parents[1]/'config/routes.json').read_text()):
    host=item['domain']
    for scheme,port,expected in [('http',80,['308']),('https',443,['200','401'] if item['name']=='stats' else ['200'])]:
        cmd=['curl','--noproxy','*','-sS','--retry','5','--retry-all-errors','--retry-delay','1','--max-time','15','--resolve',f'{host}:{port}:{a.address}','-o','/dev/null','-w','%{http_code}',f'{scheme}://{host}/']
        if not a.trusted: cmd.insert(1,'-k')
        r=subprocess.run(cmd,capture_output=True,text=True)
        print(f'{scheme}://{host}: {r.stdout}',flush=True)
        if r.returncode or r.stdout not in expected: raise SystemExit(r.stderr or 'Unexpected HTTP status')
