import requests,json
B='http://localhost:8140'
def S(u,p):
    s=requests.Session();r=s.post(B+'/api/auth/login',json={'username':u,'password':p});assert r.ok,r.text;return s
a=S('admin','admin123')
# operator baru dengan password sementara
r=a.post(B+'/api/users',json={'username':'dewi','full_name':'Dewi Lestari','role':'operator','projects':[1]});print('dewi',r.json())
json.dump({'dewi':r.json().get('temp_password')},open('creds.json','w'))
# permintaan edit: budi -> lokasi milik sari
b=S('budi','budi12345')
locs=a.get(B+'/api/locations?size=100',headers={'X-Project':'1'}).json()['rows']
sari=[l for l in locs if l['owner_id']==2]
for l in sari[:2]:
    print('req',b.post(B+'/api/edit-requests',headers={'X-Project':'1'},json={'location_id':l['id'],'message':'Lanjutkan foto yang kurang'}).status_code)
# project setup
r=a.post(B+'/api/projects',json={'name':'BTS Jatim','prefix':'BTS','color':'#3b7be0','members':[]});pid=r.json()['id'];print('setup pid',pid)
h={'X-Project':str(pid)}
# isi awal = pengaturan bawaan BAA (status Check sampai dikonfirmasi admin)
print(a.put(B+f'/api/projects/{pid}/members',json={'members':[2,3,6]}).json()['setup'])
