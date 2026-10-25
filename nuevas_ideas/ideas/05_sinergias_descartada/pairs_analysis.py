import json,statistics as st,itertools,math,random
L=json.load(open(__import__('pathlib').Path(__file__).resolve().parents[2]/'data'/'logs_2026.json'))
def phi_of(a,b):
    n=len(a);pa=sum(a)/n;pb=sum(b)/n
    va=pa*(1-pa);vb=pb*(1-pb)
    if va==0 or vb==0:return 0.0
    return (sum((x-pa)*(y-pb) for x,y in zip(a,b))/n)/math.sqrt(va*vb)
rows=[]
for ab,team in L.items():
    pl=sorted(team.items(),key=lambda kv:-st.mean(g['min'] for g in kv[1].values()))[:8]
    for (na,ga),(nb,gb) in itertools.permutations(pl,2):
        for ka,kb in (('ast','pts'),('pts','pts')):
            if ka==kb and na>nb:continue
            ids=sorted([i for i in ga if i in gb and ga[i]['min']>=10 and gb[i]['min']>=10])
            if len(ids)<40:continue
            la=math.floor(st.median([ga[i][ka] for i in ga]))+0.5
            lb=math.floor(st.median([gb[i][kb] for i in gb]))+0.5
            da=[1 if ga[i][ka]>la else 0 for i in ids];db=[1 if gb[i][kb]>lb else 0 for i in ids]
            h=len(ids)//2
            rows.append(dict(kind=f"{ka}->{kb}",team=ab,a=na,b=nb,n=len(ids),phi1=phi_of(da[:h],db[:h]),phi2=phi_of(da[h:],db[h:]),phi=phi_of(da,db)))
for kind in ('ast->pts','pts->pts'):
    R=[r for r in rows if r['kind']==kind]
    p1=[r['phi1'] for r in R];p2=[r['phi2'] for r in R]
    mx=sum(p1)/len(p1);my=sum(p2)/len(p2)
    corr=sum((x-mx)*(y-my) for x,y in zip(p1,p2))/math.sqrt(sum((x-mx)**2 for x in p1)*sum((y-my)**2 for y in p2))
    top=sorted(R,key=lambda r:-r['phi1'])[:max(8,len(R)//10)]
    print(f"{kind}: pares={len(R)} phi medio 1a mitad={mx:+.3f} 2a mitad={my:+.3f} | correlación 1a-2a mitad={corr:+.3f}")
    print(f"   mejores {len(top)} pares de la 1a mitad: phi 1a={sum(r['phi1'] for r in top)/len(top):+.3f} -> 2a mitad={sum(r['phi2'] for r in top)/len(top):+.3f}")
    # same-direction rate under independence-corrected: excess prob of both-same
print("\nMejores pares ast->pts (temporada completa):")
for r in sorted([r for r in rows if r['kind']=='ast->pts'],key=lambda r:-r['phi'])[:8]:
    print(f"  {r['team']:4s} {r['a']} (ast) -> {r['b']} (pts)  n={r['n']}  phi={r['phi']:+.2f}  (1a {r['phi1']:+.2f} / 2a {r['phi2']:+.2f})")
# permutation null: shuffle game order of b to see max phi expected by chance
random.seed(1)
mx=[]
for _ in range(200):
    best=-9
    for r in random.sample([r for r in rows if r['kind']=='ast->pts'],111):
        n=r['n'];a=[random.random()<0.45 for _ in range(n)];b=[random.random()<0.45 for _ in range(n)]
        best=max(best,phi_of([int(x) for x in a],[int(x) for x in b]))
    mx.append(best)
print(f"\nPor puro azar, el mejor de 111 pares independientes tendría phi ~ {st.mean(mx):+.2f} (rango {min(mx):+.2f} a {max(mx):+.2f})")
