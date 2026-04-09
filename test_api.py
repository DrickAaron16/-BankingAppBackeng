import urllib.request, json, urllib.error

# Login
data = json.dumps({'email': 'client@bank.com', 'password': 'client123'}).encode()
req = urllib.request.Request(
    'http://localhost:5000/auth/login',
    data=data,
    headers={'Content-Type': 'application/json'}
)
res = urllib.request.urlopen(req)
body = json.loads(res.read())
token = body['token']
print('Login OK')

# Comptes
req2 = urllib.request.Request(
    'http://localhost:5000/api/accounts/',
    headers={'Authorization': 'Bearer ' + token}
)
try:
    res2 = urllib.request.urlopen(req2)
    accounts = json.loads(res2.read())
    print(f'Comptes ({len(accounts)}):')
    for a in accounts:
        print(f"  {a['numero']} | {a['type']} | {a['solde']} {a['devise']}")
except urllib.error.HTTPError as e:
    print('ERREUR:', e.code, e.read().decode())
