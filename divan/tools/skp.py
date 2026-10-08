import struct, sys, json, math

class P:
    def __init__(s, d, pos, count, classes):
        s.d=d; s.p=pos; s.count=count; s.classes=dict(classes); s.objs={}
    def u8(s): v=s.d[s.p]; s.p+=1; return v
    def u16(s): v=struct.unpack_from('<H',s.d,s.p)[0]; s.p+=2; return v
    def u32(s): v=struct.unpack_from('<I',s.d,s.p)[0]; s.p+=4; return v
    def f64(s,n=1):
        v=struct.unpack_from('<%dd'%n,s.d,s.p); s.p+=8*n; return v
    def hdr(s):
        w=s.u16(); assert w==0,(hex(s.p),w)
        k=s.u8()
        if k==0: return None
        assert 1<=k<=5,(hex(s.p),k)
        v=int.from_bytes(s.d[s.p:s.p+k-1],'little'); s.p+=k-1; return v
    def obj(s):
        at=s.p
        t=s.u16()
        if t==0: return None
        if t==0xffff:
            sch=s.u16(); ln=s.u16(); name=s.d[s.p:s.p+ln].decode(); s.p+=ln
            s.classes[s.count]=name; s.count+=1
            cls=name
        elif t&0x8000:
            cls=s.classes[t&0x7fff]
        else:
            return s.objs[t]
        idx=s.count; s.count+=1
        o={'cls':cls,'idx':idx,'at':at}
        s.objs[idx]=o
        getattr(s,'r_'+cls)(o)
        return o
    def r_CVertex(s,o):
        o['id']=s.hdr(); o['p']=s.f64(3)
    def de(s):  # drawing element 10 bytes
        b=s.d[s.p:s.p+10]; s.p+=10; return b.hex()
    def r_CEdge(s,o):
        o['id']=s.hdr(); o['de']=s.de()
        o['v1']=s.obj(); o['v2']=s.obj(); o['curve']=s.obj()
    def r_CCurve(s,o):
        o['id']=s.hdr(); o['b']=s.u8(); o['n']=s.u32()
    def r_CArcCurve(s,o):
        s.r_CCurve(o)
        v=s.f64(14)
        o['center']=v[0:3]; o['normal']=v[3:6]; o['xaxis']=v[6:9]; o['a0']=v[9]; o['a1']=v[10]; o['yaxis']=v[11:14]
    def r_CFace(s,o):
        o['id']=s.hdr(); o['de']=s.de(); o['plane']=s.f64(4)
        n=s.u32(); o['loops']=[s.obj() for _ in range(n)]
        o['tail']=s.d[s.p:s.p+2].hex(); s.p+=2
    def r_CLoop(s,o):
        o['id']=s.hdr(); o['b1']=s.u8(); o['outer']=s.u8()
        o['first']=s.obj()
    def r_CEdgeUse(s,o):
        o['id']=s.hdr(); o['edge']=s.obj(); o['rev']=s.u8(); o['loop']=s.obj(); o['next']=s.obj()

def entities(d, pos, count, classes, n):
    p=P(d,pos,count,classes)
    ents=[]
    for i in range(n):
        try:
            ents.append(p.obj())
        except Exception as e:
            print('stop at entity',i,'pos',p.p,'err',repr(e),file=sys.stderr); break
    return p, ents

def _str(s):
    assert s.d[s.p:s.p+3]==b'\xff\xfe\xff',hex(s.p)
    n=s.d[s.p+3]; s.p+=4
    v=s.d[s.p:s.p+2*n].decode('utf-16le'); s.p+=2*n; return v
P.str=_str
def r_CSkFont(s,o):
    o['id']=s.hdr(); o['name']=s.str(); s.p+=2; o['size']=s.u32(); s.u8(); o['h']=s.f64()[0]
P.r_CSkFont=r_CSkFont
def _dimhead(s,o):
    o['id']=s.hdr(); o['de']=s.de(); o['text']=s.str(); o['font']=s.obj(); o['b']=s.u8(); o['k']=s.u32()
def r_CDimensionLinear(s,o):
    _dimhead(s,o)
    o['ends']=[]
    for _ in range(2):
        a=s.u32(); b=s.u32(); pt=s.f64(3); ref=s.obj(); rest=s.d[s.p:s.p+10].hex(); s.p+=10
        o['ends'].append({'a':a,'b':b,'pt':pt,'ref':ref,'rest':rest})
    o['v1']=s.f64(3); o['v2']=s.f64(3); o['flag']=s.u32(); o['off']=s.f64()[0]; o['x']=s.f64()[0]; o['tail']=s.u32()
P.r_CDimensionLinear=r_CDimensionLinear
def r_CDimensionRadial(s,o):
    _dimhead(s,o); o['arc']=s.obj(); o['vals']=s.f64(2); o['tail']=s.u8()
P.r_CDimensionRadial=r_CDimensionRadial
