import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import geom as g
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def prism(poly2d, axis, a0, a1):
    """Extrude 2D polygon. axis='y': poly in (X,Z), extrude Y a0..a1; axis='x': poly in (Y,Z), extrude X."""
    def P(u, v, w):
        return (u, w, v) if axis == 'y' else (w, u, v)
    f0 = [P(u, v, a0) for u, v in poly2d]
    f1 = [P(u, v, a1) for u, v in poly2d]
    faces = [f0, f1]
    n = len(poly2d)
    for i in range(n):
        j = (i + 1) % n
        faces.append([f0[i], f0[j], f1[j], f1[i]])
    return faces

def box(x0, x1, y0, y1, z0, z1, drop=()):
    f = prism([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], 'y', y0, y1)
    return [x for i, x in enumerate(f) if i not in drop]

def parts():
    out = []
    out.append(('back', prism(g.back_outline(), 'y', g.D_PANEL, g.D), '#e8e4dc'))
    out.append(('panelL', prism(g.panel_outline(g.H_HI), 'x', 0, g.T_L), '#f4f2ee'))
    out.append(('panelR', prism(g.panel_outline(g.H_LO), 'x', g.W - g.T_R, g.W), '#f4f2ee'))
    out.append(('base', box(g.T_L, g.W - g.T_R, 0, g.D_PANEL, g.Z_BASE0, g.Z_BASE1, drop=(4,)), '#dcd8d0'))
    xm = g.T_L + g.CUSHION_W
    out.append(('c1', box(g.T_L, xm, 0, g.D_PANEL, g.Z_BASE1, g.Z_SEAT, drop=(2,)), '#ffffff'))
    out.append(('c2', box(xm, g.W - g.T_R, 0, g.D_PANEL, g.Z_BASE1, g.Z_SEAT, drop=(2,)), '#ffffff'))
    return out

def render(path, elev=22, azim=-58):
    fig = plt.figure(figsize=(8, 7))
    ax = fig.add_subplot(111, projection='3d')
    allf, cols = [], []
    for name, faces, col in parts():
        allf += faces; cols += [col] * len(faces)
    ax.add_collection3d(Poly3DCollection(allf, facecolors=cols, edgecolors='#333333', linewidths=0.6))
    ax.set_xlim(-5, 112); ax.set_ylim(-10, 70); ax.set_zlim(0, 95)
    ax.set_box_aspect((117, 80, 95))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    fig.savefig(path, dpi=110, bbox_inches='tight', facecolor='white')

if __name__ == '__main__':
    render(sys.argv[1])
    render(sys.argv[2], elev=18, azim=-130)
