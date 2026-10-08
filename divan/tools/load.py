import sys, math
sys.path.insert(0, __file__.rsplit('/',1)[0])
import skp
base={0x25:'CEdge',0x27:'CVertex',0x2a:'CCurve',0x106:'CFace',0x108:'CLoop',0x10a:'CEdgeUse',0x1395:'CArcCurve'}
def load(path):
    d=open(path,'rb').read()
    pc,ec=skp.entities(d,126506,0x1392,{k:v for k,v in base.items() if k!=0x1395},34)
    pt,et=skp.entities(d,130552,0x1405,base,156)
    return pc,pt
