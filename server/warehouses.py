"""Warehouse geometry and persistent configuration; existing DB uses Settings."""
import copy,math
from sqlalchemy import select
from .models import Setting,Zone
RECT=[[0,0],[1000,0],[1000,1000],[0,1000]]
def config(s):
    setting=s.get(Setting,'warehouses')
    if setting:return copy.deepcopy(setting.value)
    zones=list(s.scalars(select(Zone)))
    objects=s.get(Setting,'map_objects');objects=objects.value.get('objects',[]) if objects else []
    width=max([2000]+[z.x+z.cols*116+40 for z in zones]+[o['x']+o['width']+40 for o in objects])
    height=max([1000]+[z.y+z.rows*112+120 for z in zones]+[o['y']+o['height']+40 for o in objects])
    return {'items':[{'id':'main','name':'기존 창고','width':width,'height':height,'points':RECT,'active':True}], 'zones':{}}
def save(s,cfg):
    item=s.get(Setting,'warehouses') or Setting(key='warehouses');item.value=copy.deepcopy(cfg);s.add(item)
def wid(cfg,zid):return cfg['zones'].get(zid,'main')
def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def on(a,b,p):return abs(cross(a,b,p))<1e-7 and min(a[0],b[0])-1e-7<=p[0]<=max(a[0],b[0])+1e-7 and min(a[1],b[1])-1e-7<=p[1]<=max(a[1],b[1])+1e-7
def intersects(a,b,c,d):
    return (cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)
def valid(points):
    if not isinstance(points,list) or not 3<=len(points)<=20:return False
    if any(not isinstance(p,list) or len(p)!=2 or any(not isinstance(n,(int,float)) or not math.isfinite(n) or not 0<=n<=1000 for n in p) for p in points):return False
    if len(set(map(tuple,points)))!=len(points):return False
    n=len(points)
    if abs(sum(points[i][0]*points[(i+1)%n][1]-points[(i+1)%n][0]*points[i][1] for i in range(n)))<1:return False
    for i in range(n):
        for j in range(i+1,n):
            if j==i+1 or (i==0 and j==n-1):continue
            if intersects(points[i],points[(i+1)%n],points[j],points[(j+1)%n]):return False
    return True
def inside(p,poly):
    yes=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if on(a,b,p):return True
        if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:yes=not yes
    return yes
def fits(w,x,y,width,height):
    poly=[[a*w['width']/1000,b*w['height']/1000] for a,b in w['points']]
    rect=[[x,y],[x+width,y],[x+width,y+height],[x,y+height]]
    if not all(inside(p,poly) for p in rect):return False
    for a,b in zip(rect,rect[1:]+rect[:1]):
        for c,d in zip(poly,poly[1:]+poly[:1]):
            if cross(a,b,c)*cross(a,b,d)<0 and cross(c,d,a)*cross(c,d,b)<0:return False
        if not inside([(a[0]+b[0])/2,(a[1]+b[1])/2],poly):return False
    return not any(x+1e-7<a<x+width-1e-7 and y+1e-7<b<y+height-1e-7 for a,b in poly)
