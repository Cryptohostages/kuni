"""Собирает PDF: инструкция, итоговый чертёж 1:1, выкройки 1:1, исходный чертёж из .skp."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import geom as g  # noqa: E402

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.pdfgen import canvas as rl_canvas  # noqa: E402

import matplotlib  # noqa: E402

_FD = os.path.join(os.path.dirname(matplotlib.__file__), 'mpl-data/fonts/ttf')
pdfmetrics.registerFont(TTFont('F', os.path.join(_FD, 'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('FB', os.path.join(_FD, 'DejaVuSans-Bold.ttf')))

PW, PH = 210.0, 297.0
MARGIN = 7.0
TAB = 5.0
GRAY = 0.86
DASH_FOLD = [1.6, 1.0]
DASH_REV = [3.0, 0.8, 0.5, 0.8]


def fmt(v):
    v = round(v, 1)
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return ('%.1f' % v).replace('.', ',')


def fmt2(v):
    s = ('%.2f' % v).rstrip('0').rstrip('.')
    return s.replace('.', ',')


class Pdf:
    def __init__(self, path):
        self.c = rl_canvas.Canvas(path, pagesize=A4)
        self.c.setTitle('Диванчик — макет по чертежу')
        self.c.setAuthor('Claude Code')
        self.page_no = 0
        self.extents = []
        self._begin()

    def _begin(self, landscape=False):
        self.page_no += 1
        self.c.setPageSize((297 * mm, 210 * mm) if landscape else A4)
        self.c.scale(mm, mm)
        self.c.setLineJoin(1)
        self.c.setLineCap(1)

    def new_page(self, landscape=False):
        self.c.showPage()
        self._begin(landscape)

    def save(self):
        self.c.showPage()
        self.c.save()

    # --- примитивы (мм) ---
    def lw(self, w):
        self.c.setLineWidth(w)

    def dash(self, d=None):
        if d:
            self.c.setDash(d, 0)
        else:
            self.c.setDash([], 0)

    def line(self, a, b, w=0.25, d=None, col=(0, 0, 0)):
        self.c.setStrokeColorRGB(*col)
        self.lw(w)
        self.dash(d)
        self.c.line(a[0], a[1], b[0], b[1])
        self.dash()

    def poly(self, pts, close=True, w=0.25, d=None, fill=None, stroke=True, col=(0, 0, 0)):
        p = self.c.beginPath()
        p.moveTo(*pts[0])
        for q in pts[1:]:
            p.lineTo(*q)
        if close:
            p.close()
        self.c.setStrokeColorRGB(*col)
        if fill is not None:
            if isinstance(fill, (int, float)):
                self.c.setFillGray(fill)
            else:
                self.c.setFillColorRGB(*fill)
        self.lw(w)
        self.dash(d)
        self.c.drawPath(p, stroke=1 if stroke else 0, fill=1 if fill is not None else 0)
        self.dash()
        self.c.setFillGray(0)

    def text(self, x, y, s, size=3.0, bold=False, anchor='l', rot=0, col=(0, 0, 0)):
        self.c.saveState()
        self.c.setFillColorRGB(*col)
        self.c.translate(x, y)
        if rot:
            self.c.rotate(rot)
        self.c.setFont('FB' if bold else 'F', size)
        if not rot and anchor == 'l':
            wd = pdfmetrics.stringWidth(s, 'FB' if bold else 'F', size)
            self.max_x = max(getattr(self, 'max_x', 0), x + wd)
            self.extents.append((self.page_no, x, y, x + wd, s))
        if anchor == 'c':
            self.c.drawCentredString(0, 0, s)
        elif anchor == 'r':
            self.c.drawRightString(0, 0, s)
        else:
            self.c.drawString(0, 0, s)
        self.c.restoreState()

    def push(self, x, y, rot=0):
        self.c.saveState()
        self.c.translate(x, y)
        if rot:
            self.c.rotate(rot)

    def pop(self):
        self.c.restoreState()

    def arrow(self, tip, direction, size=1.6, col=(0, 0, 0)):
        dx, dy = direction
        n = math.hypot(dx, dy)
        dx, dy = dx / n, dy / n
        bx, by = tip[0] - dx * size, tip[1] - dy * size
        px, py = -dy * size * 0.28, dx * size * 0.28
        self.poly([tip, (bx + px, by + py), (bx - px, by - py)], fill=col, w=0.05, col=col)

    def dim(self, a, b, off, text=None, size=2.6, col=(0.1, 0.1, 0.1), ext=True, kind='a'):
        """Размер между a и b. kind: 'h' горизонтальный, 'v' вертикальный, 'a' по линии. off — смещение линии."""
        if kind == 'h':
            y = max(a[1], b[1]) + off if off > 0 else min(a[1], b[1]) + off
            pa, pb = (a[0], y), (b[0], y)
            val = abs(b[0] - a[0])
        elif kind == 'v':
            x = max(a[0], b[0]) + off if off > 0 else min(a[0], b[0]) + off
            pa, pb = (x, a[1]), (x, b[1])
            val = abs(b[1] - a[1])
        else:
            dx, dy = b[0] - a[0], b[1] - a[1]
            n = math.hypot(dx, dy)
            nx, ny = -dy / n, dx / n
            pa = (a[0] + nx * off, a[1] + ny * off)
            pb = (b[0] + nx * off, b[1] + ny * off)
            val = n
        if ext:
            for p, q in ((a, pa), (b, pb)):
                d = (q[0] - p[0], q[1] - p[1])
                L = math.hypot(*d)
                if L > 0.3:
                    e = (q[0] + d[0] / L * 1.2, q[1] + d[1] / L * 1.2)
                    s = (p[0] + d[0] / L * 0.6, p[1] + d[1] / L * 0.6)
                    self.line(s, e, w=0.12, col=col)
        self.line(pa, pb, w=0.15, col=col)
        d = (pb[0] - pa[0], pb[1] - pa[1])
        self.arrow(pb, d, col=col)
        self.arrow(pa, (-d[0], -d[1]), col=col)
        ang = math.degrees(math.atan2(d[1], d[0]))
        if ang > 90.1 or ang < -89.9:
            ang += 180
        mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        r = math.radians(ang)
        tx, ty = mx - math.sin(r) * 0.7, my + math.cos(r) * 0.7
        self.text(tx, ty, text if text is not None else fmt(val), size=size, anchor='c', rot=ang, col=col)


# ---------------------------------------------------------------- выкройки
def tab_insets(theta, t):
    """Отступ верхней кромки клапана от угла с внутренним углом theta (град.)."""
    base = 0.6 + 0.5 * t
    if theta < 179:
        return max(base, t / math.tan(math.radians(theta / 2)) + 0.4)
    return base


def strip_size(segs, w):
    L = sum(s[1] for s in segs)
    return L + 6.0, w + 2 * TAB


def draw_strip(pdf, segs, angles, w, title):
    """Лента: segs=[(имя, длина, 'line'|'arc')], angles — внутренние углы в узлах (len(segs)+1),
    рисуется от (0, TAB): лента y∈[TAB, TAB+w], клапаны ниже и выше."""
    y0, y1 = TAB, TAB + w
    xs = [0.0]
    for s in segs:
        xs.append(xs[-1] + s[1])
    L = xs[-1]
    fold_intervals = {0: [], 1: []}
    tabs = []
    for i, (nm, ln, kind) in enumerate(segs):
        xa, xb = xs[i], xs[i + 1]
        if kind == 'arc':
            ta = 4.0
            span = xb - xa - 1.2
            n = max(1, int(span // 3.2))
            pitch = span / n
            for k in range(n):
                x0 = xa + 0.6 + k * pitch + 0.35
                x1 = x0 + pitch - 0.7
                for side in (0, 1):
                    fold_intervals[side].append((x0, x1))
                    tabs.append((side, x0, x1, x0 + 0.5, x1 - 0.5, ta))
            continue
        t = TAB
        while t >= 2.0:
            ia, ib = tab_insets(angles[i], t), tab_insets(angles[i + 1], t)
            if (xb - ib) - (xa + ia) >= 1.0:
                break
            t -= 0.5
        if t < 2.0:
            continue
        for side in (0, 1):
            fold_intervals[side].append((xa + 0.6, xb - 0.6))
            tabs.append((side, xa + 0.6, xb - 0.6, xa + ia, xb - ib, t))
    # клапаны
    for side, b0, b1, t0, t1, t in tabs:
        if side == 0:
            pts = [(b0, y0), (b1, y0), (t1, y0 - t), (t0, y0 - t)]
        else:
            pts = [(b0, y1), (b1, y1), (t1, y1 + t), (t0, y1 + t)]
        pdf.poly(pts, fill=GRAY, w=0.25)
        pdf.line(pts[0], pts[1], w=0.3, col=(1, 1, 1))  # стираем линию основания...
        pdf.line(pts[0], pts[1], w=0.25, d=DASH_FOLD)   # ...и рисуем сгиб
    # торцевой клапан
    et = [(L, y0 + 0.8), (L + 6, y0 + 2.5), (L + 6, y1 - 2.5), (L, y1 - 0.8)]
    pdf.poly(et, fill=GRAY, w=0.25)
    # длинные кромки: сгиб под клапанами, рез в остальных местах
    for side, y in ((0, y0), (1, y1)):
        iv = sorted(fold_intervals[side])
        cur = 0.0
        for a, b in iv:
            if a > cur:
                pdf.line((cur, y), (a, y), w=0.3)
            pdf.line((a, y), (b, y), w=0.25, d=DASH_FOLD)
            cur = b
        if cur < L:
            pdf.line((cur, y), (L, y), w=0.3)
    pdf.line((0, y0), (0, y1), w=0.3)
    pdf.line((L, y0), (L, y1), w=0.25, d=DASH_FOLD)
    # сгибы в углах
    for i in range(1, len(segs)):
        th = angles[i]
        d = DASH_REV if th > 180.5 else DASH_FOLD
        pdf.line((xs[i], y0), (xs[i], y1), w=0.25, d=d)
    # подписи
    fs = min(2.2, w * 0.24)
    longest = max(range(len(segs)), key=lambda k: segs[k][1])
    for i, (nm, ln, kind) in enumerate(segs):
        xm = (xs[i] + xs[i + 1]) / 2
        lab = fmt(ln) if ln < 20 else '%s %s' % (nm, fmt(ln))
        yc = y0 + w / 2 - fs * 0.35
        if i == longest and title:
            pdf.text(xm, yc + fs * 0.75, title, size=fs, bold=True, anchor='c')
            yc -= fs * 0.75
        pdf.text(xm, yc, lab, size=fs if ln >= 12 else fs * 0.8, anchor='c')
    return L + 6.0, w + 2 * TAB


def place_strip(pdf, x, y, segs, angles, w, title, vertical=False):
    W_, H_ = strip_size(segs, w)
    if vertical:
        pdf.push(x + H_, y, 90)
    else:
        pdf.push(x, y)
    draw_strip(pdf, segs, angles, w, title)
    pdf.pop()
    return (H_, W_) if vertical else (W_, H_)


def band_angles(path_pts, breaks):
    """Внутренние углы в точках разрыва замкнутого пути (против часовой)."""
    n = len(path_pts)
    res = []
    for i in breaks:
        p0, p1, p2 = path_pts[(i - 1) % n], path_pts[i % n], path_pts[(i + 1) % n]
        a = math.atan2(p0[1] - p1[1], p0[0] - p1[0])
        b = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        res.append(math.degrees(a - b) % 360)
    return res


def panel_band(h_back):
    """Сегменты ленты боковины в порядке против часовой и углы. Возвращает (полоса A, углы A, полоса B, углы B)."""
    arc = list(reversed(g.arc_points(48)))  # от излома к передней грани
    # путь против часовой: (0,0) → (LEG,0) → (LEG,U) → (D,U) → (D,h) → излом → дуга → (0,ZF)
    path = [(0, 0), (g.LEG_D, 0), (g.LEG_D, g.Z_UNDER), (g.D_PANEL, g.Z_UNDER), (g.D_PANEL, h_back)] + arc
    i_corner = {
        'p00': 0, 'leg': 1, 'legin': 2, 'backlow': 3, 'top': 4, 'kink': 5, 'front': len(path) - 1,
    }
    ang = dict(zip(i_corner.keys(), band_angles(path, list(i_corner.values()))))
    segs = {s[0]: s for s in g.panel_segments(h_back)}
    # полоса A: скос → дуга → перед (видимая), полоса B: низ ножки → ножка → низ → зад
    A = [segs['скос'], segs['дуга R40,5'], segs['перед']]
    angA = [ang['top'], ang['kink'], ang['front'], ang['p00']]
    B = [segs['низ ножки'], segs['ножка'], segs['низ'], segs['зад (к спинке)']]
    angB = [ang['p00'], ang['leg'], ang['legin'], ang['backlow'], ang['top']]
    return A, angA, B, angB


def back_band():
    o = g.back_outline()
    ang = band_angles(o, list(range(len(o))))
    segs = g.back_segments()
    # полоса 1: низ + правый торец; полоса 2: верх низкой, скос, верх высокой, левый торец
    S1, a1 = segs[0:2], [ang[0], ang[1], ang[2]]
    S2, a2 = segs[2:6], [ang[2], ang[3], ang[4], ang[5], ang[0]]
    return S1, a1, S2, a2


def draw_face(pdf, x, y, pts, label_lines, ticks=(), mirror=False):
    """Грань-контур. pts в локальных мм (min = 0). ticks: [(точка, направление, длина)]."""
    P = [(x + (-p[0] if mirror else p[0]), y + p[1]) for p in pts]
    pdf.poly(P, w=0.3)
    for (px, py), (dx, dy), L in ticks:
        pdf.line((x + px, y + py), (x + px + dx * L, y + py + dy * L), w=0.2, col=(0.35, 0.35, 0.35))
    return P


def box_net(pdf, x, y, Lx, Ly, h, t, title, sub=''):
    """Развёртка коробки (крышка — к задней стенке). Возвращает (w, hgt)."""
    X0, X1 = x + h, x + h + Lx
    yF0, yF1 = y, y + h               # передняя стенка
    yB1 = yF1 + Ly                    # дно
    yK1 = yB1 + h                     # задняя стенка
    yT1 = yK1 + Ly                    # крышка
    cut, fold = [], []
    # дно с четырьмя сторонами: сгибы по периметру дна
    fold += [((X0, yF1), (X1, yF1)), ((X0, yB1), (X1, yB1)), ((X0, yF1), (X0, yB1)), ((X1, yF1), (X1, yB1)),
             ((X0, yK1), (X1, yK1))]
    # передняя стенка: низ и бока — рез
    cut += [((X0, yF0), (X1, yF0)), ((X0, yF0), (X0, yF1)), ((X1, yF0), (X1, yF1))]
    # задняя стенка: бока — рез
    cut += [((X0, yB1), (X0, yK1)), ((X1, yB1), (X1, yK1))]
    # боковые стенки
    for xa, xb, outer in ((x, X0, x), (X1, X1 + h, X1 + h)):
        cut.append(((outer, yF1), (outer, yB1)))
        # клапаны на торцах боковых стенок (к передней и задней)
        tb = [(xa + 0.6, yF1), (xb - 0.6, yF1), (xb - 0.6 - min(t, h) * 0.3, yF1 - min(t, h - 0.5)),
              (xa + 0.6 + min(t, h) * 0.3, yF1 - min(t, h - 0.5))]
        tt = [(xa + 0.6, yB1), (xb - 0.6, yB1), (xb - 0.6 - min(t, h) * 0.3, yB1 + min(t, h - 0.5)),
              (xa + 0.6 + min(t, h) * 0.3, yB1 + min(t, h - 0.5))]
        for tp in (tb, tt):
            pdf.poly(tp, fill=GRAY, w=0.25)
            fold.append((tp[0], tp[1]))
        cut += [((xa, yF1), (xa + 0.6, yF1)), ((xb - 0.6, yF1), (xb, yF1)),
                ((xa, yB1), (xa + 0.6, yB1)), ((xb - 0.6, yB1), (xb, yB1))]
    # крышка: клапаны слева, справа и спереди
    tl = [(X0, yK1 + 0.6), (X0, yT1 - 0.6), (X0 - t, yT1 - 0.6 - t * 0.6), (X0 - t, yK1 + 0.6 + t * 0.6)]
    tr = [(X1, yK1 + 0.6), (X1, yT1 - 0.6), (X1 + t, yT1 - 0.6 - t * 0.6), (X1 + t, yK1 + 0.6 + t * 0.6)]
    tf = [(X0 + 0.6, yT1), (X1 - 0.6, yT1), (X1 - 0.6 - t * 0.6, yT1 + t), (X0 + 0.6 + t * 0.6, yT1 + t)]
    for tp in (tl, tr, tf):
        pdf.poly(tp, fill=GRAY, w=0.25)
        fold.append((tp[0], tp[1]))
    cut += [((X0, yK1), (X0, yK1 + 0.6)), ((X0, yT1 - 0.6), (X0, yT1)),
            ((X1, yK1), (X1, yK1 + 0.6)), ((X1, yT1 - 0.6), (X1, yT1)),
            ((X0, yT1), (X0 + 0.6, yT1)), ((X1 - 0.6, yT1), (X1, yT1))]
    for a, b in cut:
        pdf.line(a, b, w=0.3)
    for a, b in fold:
        pdf.line(a, b, w=0.3, col=(1, 1, 1))
        pdf.line(a, b, w=0.25, d=DASH_FOLD)
    # подписи
    pdf.text((X0 + X1) / 2, (yF1 + yB1) / 2 + 1.5, title, size=3, bold=True, anchor='c')
    if sub:
        pdf.text((X0 + X1) / 2, (yF1 + yB1) / 2 - 2.5, sub, size=2.3, anchor='c')
    pdf.text((X0 + X1) / 2, (yK1 + yT1) / 2 - 1, 'верх (видимая сторона)', size=2.3, anchor='c', col=(0.3, 0.3, 0.3))
    pdf.text((X0 + X1) / 2, (yF0 + yF1) / 2 - 0.9, 'перед', size=min(2.3, h * 0.45), anchor='c', col=(0.3, 0.3, 0.3))
    return 2 * h + Lx, 2 * h + 2 * Ly + t


def page_header(pdf, title, sub=''):
    pdf.text(MARGIN, PH - MARGIN - 4, title, size=4.2, bold=True)
    if sub:
        pdf.text(MARGIN, PH - MARGIN - 8.5, sub, size=2.6, col=(0.25, 0.25, 0.25))
    pdf.text(PW - MARGIN, PH - MARGIN - 4, 'стр. %d' % pdf.page_no, size=2.6, anchor='r', col=(0.4, 0.4, 0.4))


def scale_bar(pdf, x, y):
    pdf.line((x, y), (x + 50, y), w=0.35)
    for k in range(0, 51, 10):
        pdf.line((x + k, y), (x + k, y + (2.2 if k % 50 == 0 else 1.2)), w=0.25)
    pdf.text(x + 53, y - 0.6, 'контроль масштаба: ровно 50 мм (печать 100%, «фактический размер»)', size=2.4)


def legend(pdf, x, y):
    pdf.line((x, y), (x + 10, y), w=0.3)
    pdf.text(x + 12, y - 0.8, 'резать', size=2.4)
    pdf.line((x + 30, y), (x + 40, y), w=0.25, d=DASH_FOLD)
    pdf.text(x + 42, y - 0.8, 'сгиб внутрь', size=2.4)
    pdf.line((x + 70, y), (x + 80, y), w=0.25, d=DASH_REV)
    pdf.text(x + 82, y - 0.8, 'сгиб в обратную сторону', size=2.4)
    pdf.poly([(x + 128, y - 1.5), (x + 136, y - 1.5), (x + 136, y + 1.5), (x + 128, y + 1.5)], fill=GRAY, w=0.2)
    pdf.text(x + 138, y - 0.8, 'клапан под клей', size=2.4)


def footer(pdf):
    legend(pdf, MARGIN, MARGIN + 7)
    scale_bar(pdf, MARGIN, MARGIN + 1)


# ---------------------------------------------------------------- страницы
def page_instructions(pdf, iso_png):
    page_header(pdf, 'Диванчик — макет по чертежу «чертеж.skp»',
                'Файл: SketchUp 2019, лист А4 в масштабе 1:1 (мм), три вида повёрнуты на 90°. Ниже — согласованная версия для сборки.')
    if iso_png and os.path.exists(iso_png):
        pdf.c.drawImage(iso_png, PW - MARGIN - 62, PH - MARGIN - 76, width=62, height=62,
                        preserveAspectRatio=True, mask='auto')
    y = PH - MARGIN - 18
    x = MARGIN

    def para(lines, size=2.9, lead=4.3, bold_first=False, indent=0):
        nonlocal y
        for i, s in enumerate(lines):
            pdf.text(x + indent, y, s, size=size, bold=(bold_first and i == 0))
            y -= lead

    para(['Габариты: длина 106,2 × глубина 60,5 × высота 87,7 мм'], size=3.3, bold_first=True)
    y -= 1.5
    para(['Детали', ], size=3.4, bold_first=True)
    rows = [
        ('1', 'Спинка', '1', 'контур по виду спереди, толщина 10'),
        ('', '', '', 'высокая часть 87,7 (слева), низкая 66,0 (справа)'),
        ('2', 'Боковина левая (высокая)', '1', 'профиль вида сбоку, зад 87,7, толщина 10,5'),
        ('3', 'Боковина правая (низкая)', '1', 'тот же профиль, зад 66,0, толщина 10,4'),
        ('4', 'Основание сиденья', '1', '85,3 × 50,5 × 4,8; низ на высоте 12,9'),
        ('5', 'Подушка', '2', '42,65 × 50,5 × 10; верх на высоте 27,7'),
        ('6', '«Пламя» (по желанию)', '1', 'только на фото, в чертеже его нет'),
    ]
    for n, name, q, d in rows:
        pdf.text(x, y, n, size=2.8)
        pdf.text(x + 5, y, name, size=2.8, bold=bool(name))
        pdf.text(x + 50, y, ('× ' + q) if q else '', size=2.8)
        pdf.text(x + 60, y, d, size=2.6)
        y -= 4.0
    y -= 2
    para(['Несостыковки в чертеже — что выбрано'], size=3.4, bold_first=True)
    notes = [
        '• Высота: на виде сбоку спинка 75, на виде спереди 87,7 (слева) и 66 (справа).',
        '   Взят вид спереди — на нём больше всего размеров. Скос боковин пересчитан под эти высоты.',
        '• Вид сверху (слева на листе) нарисован с другими числами (длина 102,3, боковины 5,7,',
        '   спинка 5,5) — не совпадает с видами спереди и сбоку (106,2; 10,5; 10). Не используется.',
        '• Подушки: на виде спереди 46,5 и 38,9, на виде сверху и на фото равные — сделаны по 42,65.',
        '• Низ правой боковины на чертеже выше на 1,4 мм (отсюда размер 26,3 вместо 27,7).',
        '   Опущена до пола, как и левая.',
        '• В файле есть лишний компонент («Компонент#1», веер с дугами) — на листе не стоит,',
        '   к дивану не относится.',
    ]
    para(notes, size=2.6, lead=3.7)
    y -= 2
    para(['Печать и материал'], size=3.4, bold_first=True)
    para([
        '• Стр. 3–5 печатать в масштабе 100% («Фактический размер», без «Вписать в страницу»).',
        '   Проверьте линейкой отрезок 50 мм внизу страницы.',
        '• Плотная бумага 160–250 г/м² (печатью внутрь) или переведите контуры на макетный картон.',
        '• Сгибы сначала продавите (тупой стороной ножа по линейке), потом гните.',
    ], size=2.6, lead=3.7)
    y -= 2
    para(['Сборка'], size=3.4, bold_first=True)
    para([
        '1. Каждая деталь — коробочка: ленту согнуть по пунктиру, клапанами приклеить к одной грани,',
        '   затем закрыть второй гранью. Вторую грань кладите зеркально (перевернуть шаблон).',
        '   Торцевой клапан ленты 1 клеится под начало ленты 2 и наоборот. На дуге — клапаны-зубчики.',
        '2. Спинку поставить на стол. Боковины приклеить к её передней грани у торцов: высокую —',
        '   со стороны высокой части спинки (слева, если смотреть спереди), низкую — справа.',
        '   Ножка боковины — спереди, задний край боковины прилегает к спинке.',
        '3. Основание сиденья вклеить между боковинами вплотную к спинке: низ на 12,9 мм от стола',
        '   (подложите брусок/стопку картона 12,9 мм). Риски на гранях боковин: 12,9 / 17,7 / 27,7.',
        '4. Сверху на основание — две подушки, вплотную к спинке.',
        '5. По желанию — «пламя» приклеить к задней стороне спинки (как на фото).',
    ], size=2.6, lead=3.7)
    y -= 2
    para(['Содержание: 1 — инструкция · 2 — итоговый чертёж 1:1 (альбомный лист) · 3–5 — выкройки 1:1 ·',
          '6 — исходный чертёж из файла (1:1)'], size=2.5, lead=3.6)


def page_views(pdf):
    """Альбомный лист: вид спереди, вид слева, вид сверху — 1:1."""
    red = (0.65, 0.05, 0.05)
    LW, LH = 297.0, 210.0
    # ---- вид спереди
    fx, fy = 34, 96
    P = lambda X, Z: (fx + X, fy + Z)  # noqa: E731
    pdf.poly([P(*p) for p in g.back_outline()], w=0.35)
    for x0, x1, h in ((0, g.T_L, g.H_HI), (g.W - g.T_R, g.W, g.H_LO)):
        pdf.poly([P(x0, 0), P(x1, 0), P(x1, h), P(x0, h)], w=0.35, fill=1.0)
        for z in (g.Z_FRONT, g.ARC_END[1]):
            pdf.line(P(x0, z), P(x1, z), w=0.2)
    xb0, xb1 = g.T_L, g.W - g.T_R
    pdf.poly([P(xb0, g.Z_BASE0), P(xb1, g.Z_BASE0), P(xb1, g.Z_BASE1), P(xb0, g.Z_BASE1)], w=0.35, fill=1.0)
    xm = g.T_L + g.CUSHION_W
    for a, b in ((xb0, xm), (xm, xb1)):
        pdf.poly([P(a, g.Z_BASE1), P(b, g.Z_BASE1), P(b, g.Z_SEAT), P(a, g.Z_SEAT)], w=0.35, fill=1.0)
    pdf.text(fx + 33, fy + 62, 'ВИД СПЕРЕДИ', size=3.4, bold=True, anchor='c', col=(0.25, 0.25, 0.25))
    pdf.dim(P(0, g.H_HI), P(g.W, g.H_HI), 14, kind='h', col=red)
    pdf.dim(P(0, g.H_HI), P(g.X_HI_END, g.H_HI), 5.5, kind='h', col=red)
    pdf.dim(P(g.X_HI_END, g.H_HI), P(g.X_LO_START, g.H_LO), 5.5, kind='h', col=red)
    pdf.dim(P(g.X_LO_START, g.H_LO), P(g.W, g.H_LO), 5.5 + g.H_HI - g.H_LO, kind='h', col=red)
    pdf.dim(P(0, 0), P(g.T_L, 0), -5, kind='h', col=red)
    pdf.dim(P(g.T_L, 0), P(g.W - g.T_R, 0), -5, kind='h', col=red)
    pdf.dim(P(g.W - g.T_R, 0), P(g.W, 0), -5, kind='h', col=red)
    pdf.dim(P(0, 0), P(0, g.H_HI), -6, kind='v', col=red)
    pdf.dim(P(0, 0), P(0, g.Z_BASE0), -13, kind='v', col=red)
    pdf.dim(P(0, g.Z_BASE0), P(0, g.Z_BASE1), -13, kind='v', col=red, text='4,8', size=2.2)
    pdf.dim(P(0, g.Z_BASE1), P(0, g.Z_SEAT), -13, kind='v', col=red, size=2.2)
    pdf.dim(P(0, 0), P(0, g.Z_SEAT), -20, kind='v', col=red)
    pdf.dim(P(g.W, 0), P(g.W, g.H_LO), 6, kind='v', col=red)
    pdf.dim(P(g.X_HI_END, g.H_HI), P(g.X_LO_START, g.H_LO), 3, kind='a', col=red)
    pdf.text(fx + g.T_L + g.CUSHION_W / 2, fy + g.Z_BASE1 + 3.5, fmt2(g.CUSHION_W), size=2.4, anchor='c', col=red)
    pdf.text(fx + xm + g.CUSHION_W / 2, fy + g.Z_BASE1 + 3.5, fmt2(g.CUSHION_W), size=2.4, anchor='c', col=red)

    # ---- вид слева (зад слева, перед справа)
    sx, sy = 200, 96
    S = lambda Y, Z: (sx + (g.D - Y) - g.D_SLAB, sy + Z)  # noqa: E731
    slab = [S(g.D, 0), S(g.D_PANEL, 0), S(g.D_PANEL, g.H_HI), S(g.D, g.H_HI)]
    pdf.poly(slab, w=0.35)
    pdf.poly([S(*p) for p in g.panel_outline(g.H_HI, 32)], w=0.35, fill=1.0)
    pdf.poly([S(*p) for p in g.panel_outline(g.H_LO, 32)], w=0.2, d=[1.2, 0.8], col=(0.35, 0.35, 0.35))
    q = S(g.D, g.H_LO)
    pdf.line((q[0] - 3, q[1]), (q[0] - 0.3, q[1]), w=0.15, col=(0.35, 0.35, 0.35))
    pdf.text(q[0] - 4, q[1] + 1.5, 'пунктир — правая', size=2.2, anchor='r', col=(0.35, 0.35, 0.35))
    pdf.text(q[0] - 4, q[1] - 1.8, 'боковина, зад 66', size=2.2, anchor='r', col=(0.35, 0.35, 0.35))
    pdf.text(sx + 20, sy + g.H_HI + 13, 'ВИД СЛЕВА', size=3.4, bold=True, anchor='c', col=(0.25, 0.25, 0.25))
    pdf.dim(S(g.D, g.H_HI), S(g.D_PANEL, g.H_HI), 5, kind='h', col=red)
    pdf.dim(S(g.D_PANEL, 0), S(g.LEG_D, 0), -5, kind='h', col=red)
    pdf.dim(S(g.LEG_D, 0), S(0, 0), -5, kind='h', col=red, size=2.2)
    pdf.dim(S(g.D_PANEL, 0), S(0, 0), -11, kind='h', col=red)
    pdf.dim(S(g.D, 0), S(0, 0), -17, kind='h', col=red)
    pdf.dim(S(g.ARC_END[0], g.ARC_END[1]), S(0, g.ARC_END[1]), 4, kind='h', col=red, text='24,4')
    pdf.dim(S(0, 0), S(0, g.Z_FRONT), 5, kind='v', col=red, text='22,9')
    pdf.dim(S(0, 0), S(0, g.ARC_END[1]), 13, kind='v', col=red, text='40,5')
    pdf.dim(S(g.LEG_D + 8, 0), S(g.LEG_D + 8, g.Z_UNDER), 0, kind='v', col=red, text='7,5', size=2.2, ext=False)
    c = S(*g.ARC_C)
    am = S(*g.arc_points(2)[1])
    pdf.line(c, am, w=0.12, col=red)
    pdf.arrow(am, (am[0] - c[0], am[1] - c[1]), col=red)
    pdf.text(am[0] - 13, am[1] - 4, 'R40,5', size=2.6, col=red)

    # ---- вид сверху (перед внизу)
    tx, ty = 34, 17
    T = lambda X, Y: (tx + X, ty + Y)  # noqa: E731
    pdf.poly([T(0, g.D_PANEL), T(g.W, g.D_PANEL), T(g.W, g.D), T(0, g.D)], w=0.35)
    for X in (g.X_HI_END, g.X_LO_START):
        pdf.line(T(X, g.D_PANEL), T(X, g.D), w=0.2)
    for x0, x1 in ((0, g.T_L), (g.W - g.T_R, g.W)):
        pdf.poly([T(x0, 0), T(x1, 0), T(x1, g.D_PANEL), T(x0, g.D_PANEL)], w=0.35)
        pdf.line(T(x0, g.ARC_END[0]), T(x1, g.ARC_END[0]), w=0.2)
    for a, b in ((xb0, xm), (xm, xb1)):
        pdf.poly([T(a, 0), T(b, 0), T(b, g.D_PANEL), T(a, g.D_PANEL)], w=0.35)
    pdf.text(tx + g.W / 2, ty + 30, 'ВИД СВЕРХУ', size=3.4, bold=True, anchor='c', col=(0.25, 0.25, 0.25))
    pdf.text(tx + g.W / 2, ty + 25, 'подушки', size=2.4, anchor='c', col=(0.35, 0.35, 0.35))
    pdf.dim(T(0, 0), T(g.W, 0), -6, kind='h', col=red)
    pdf.dim(T(0, 0), T(0, g.ARC_END[0]), -5, kind='v', col=red, text='24,4')
    pdf.dim(T(g.W, 0), T(g.W, g.D_PANEL), 5, kind='v', col=red)
    pdf.dim(T(g.W, g.D_PANEL), T(g.W, g.D), 5, kind='v', col=red)
    pdf.dim(T(g.W, 0), T(g.W, g.D), 13, kind='v', col=red)
    pdf.text(tx + g.W / 2, ty - 1.2 + 0, '', size=2)

    # заголовок и пояснения (справа внизу)
    nx, ny = 168, 62
    pdf.text(nx, ny + 6, 'Итоговый чертёж — масштаб 1:1, мм', size=4.0, bold=True)
    lines = [
        'Ширины и высоты — по виду спереди, глубина и профиль',
        'боковин — по виду сбоку. Красным — размеры для выкроек.',
        '',
        'Высоты от пола: низ основания 12,9 · верх основания 17,7 ·',
        'верх подушек 27,7 · перед боковины 22,9 · излом 40,5 ·',
        'низкая часть спинки 66 · высокая 87,7.',
        '',
        'Боковины: ножка спереди 9,4, просвет под боковиной 7,5,',
        'задний край боковины прилегает к спинке; спинка — на полу.',
        'Левая и правая боковины одинаковые спереди (дуга R40,5),',
        'отличаются высотой заднего края и наклоном скоса.',
    ]
    y = ny
    for s in lines:
        pdf.text(nx, y, s, size=2.6)
        y -= 4.0
    pdf.text(LW - MARGIN, MARGIN, 'стр. %d' % pdf.page_no, size=2.6, anchor='r', col=(0.4, 0.4, 0.4))


def page_back(pdf):
    page_header(pdf, 'Выкройки 1:1 — спинка', 'Две грани и две ленты шириной 10 мм. Сборка: лента по контуру, грани сверху и снизу.')
    o = g.back_outline()
    x0, y0 = MARGIN + 2, PH - MARGIN - 14 - g.H_HI
    for k, nm in enumerate(['СПИНКА — передняя грань', 'СПИНКА — задняя грань']):
        yy = y0 - k * (g.H_HI + 8)
        draw_face(pdf, x0, yy, o, [])
        pdf.text(x0 + 40, yy + 45, nm, size=3.2, bold=True, anchor='c')
        pdf.text(x0 + 40, yy + 40, 'высокая часть слева, если смотреть спереди' if k == 0
                 else 'при сборке перевернуть: сзади высокая часть справа', size=2.3, anchor='c')
        pdf.text(x0 + 40, yy + 36, 'толщина 10 мм', size=2.3, anchor='c', col=(0.3, 0.3, 0.3))
    S1, a1, S2, a2 = back_band()
    sx = x0 + g.W + 8
    w2, h2 = place_strip(pdf, sx, MARGIN + 18, S2, a2, g.D_SLAB, 'спинка, лента 2', vertical=True)
    place_strip(pdf, sx + w2 + 6, MARGIN + 18, S1, a1, g.D_SLAB, 'спинка, лента 1', vertical=True)
    footer(pdf)


def page_panels(pdf):
    page_header(pdf, 'Выкройки 1:1 — боковины',
                'Каждая боковина — 2 грани + ленты A и B. Вторую грань переверните. Риски: 12,9 / 17,7 / 27,7 от пола.')
    y_top = PH - MARGIN - 13
    x0 = MARGIN + 2

    def ticks():
        t = []
        for z in (g.Z_BASE0, g.Z_BASE1, g.Z_SEAT):
            if z < g.Z_FRONT:
                t.append(((0, z), (1, 0), 3.0))
            t.append(((g.D_PANEL, z), (-1, 0), 3.0))
        return t
    for row, (h, nm) in enumerate(((g.H_HI, 'ЛЕВАЯ (высокая)'), (g.H_LO, 'ПРАВАЯ (низкая)'))):
        yy = y_top - h - (0 if row == 0 else g.H_HI + 8)
        for k in range(2):
            xx = x0 + k * (g.D_PANEL + 6)
            draw_face(pdf, xx, yy, g.panel_outline(h, 48), [], ticks=[((p[0], p[1]), d, L) for p, d, L in ticks()])
            pdf.text(xx + 28, yy + 16, 'БОКОВИНА', size=2.8, bold=True, anchor='c')
            pdf.text(xx + 28, yy + 12.5, nm, size=2.4, anchor='c')
            pdf.text(xx + 28, yy + 9.5, 'грань %d из 2' % (k + 1), size=2.2, anchor='c', col=(0.3, 0.3, 0.3))
            pdf.text(xx + 1.5, yy + 1.5, 'перед', size=1.8, col=(0.3, 0.3, 0.3))
            pdf.text(xx + g.D_PANEL - 1.5, yy + 9, 'к спинке', size=1.8, anchor='r', rot=0, col=(0.3, 0.3, 0.3))
    AL, aAL, BL, aBL = panel_band(g.H_HI)
    AR, aAR, BR, aBR = panel_band(g.H_LO)
    cx = x0 + 2 * (g.D_PANEL + 6) + 2
    yb = MARGIN + 18
    w1, h1 = place_strip(pdf, cx, yb, BL, aBL, g.T_L, 'лев. B', vertical=True)
    place_strip(pdf, cx, yb + h1 + 4, AR, aAR, g.T_R, 'прав. A', vertical=True)
    w2, h2 = place_strip(pdf, cx + w1 + 5, yb, BR, aBR, g.T_R, 'прав. B', vertical=True)
    place_strip(pdf, cx + w1 + 5, yb + h2 + 4, AL, aAL, g.T_L, 'лев. A', vertical=True)
    pdf.text(x0, yb + 4, 'Лента A — видимая (скос, дуга, перед), лента B — низ и задний край.', size=2.4)
    pdf.text(x0, yb, 'Торцевой клапан A клеится под начало B (у пола спереди), клапан B — под начало A.', size=2.4)
    footer(pdf)


def flame_outline():
    """Декор «пламя» (по фото), в координатах спинки (X, Z). Нижняя часть — полоса под клей 8 мм."""
    def bez(p0, p1, p2, p3, n=10):
        out = []
        for i in range(1, n + 1):
            t = i / n
            a = (1 - t) ** 3
            b = 3 * (1 - t) ** 2 * t
            c = 3 * (1 - t) * t * t
            d = t ** 3
            out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
        return out
    H, L = g.H_HI, g.H_LO
    glue = 8.0
    pts = [(12, H - glue)]
    pts.append((12, H))
    cur = (12, H)
    for c1, c2, end in [
        ((11, H + 6), (9, H + 10), (13, H + 14)),       # левый язык
        ((15, H + 9), (16, H + 6), (19, H + 5)),
        ((22, H + 9), (21, H + 15), (27, H + 19)),      # второй язык
        ((28, H + 13), (29, H + 9), (32, H + 8)),
        ((34, H + 14), (38, H + 19), (45, H + 21)),     # большой язык
        ((44, H + 15), (45, H + 9), (48, H + 7)),
        ((51, H + 10), (52, H + 13), (55, H + 13)),     # малый
        ((55, H + 9), (57, H + 5), (60, H + 3)),
        ((62, H + 7), (63, H + 9), (66, H + 9)),        # над скосом
        ((65, H + 4), (66, L + 14), (70, L + 12)),
        ((76, L + 16), (84, L + 13), (82, L + 6)),      # правая «капля»
        ((81, L + 2), (78, L + 0.5), (76, L)),
    ]:
        pts += bez(cur, c1, c2, end)
        cur = end
    # обратно по контуру спинки, ниже на ширину клея
    pts += [(76, L - glue), (g.X_LO_START + 0.3, L - glue), (g.X_HI_END + 0.3, H - glue)]
    return pts


def page_seat(pdf):
    page_header(pdf, 'Выкройки 1:1 — основание, подушки, декор',
                'Крышка коробочки — видимая сторона. Подушки — 2 шт.')
    top = PH - MARGIN - 14
    hc = 2 * 10 + 2 * g.D_PANEL + 5
    for k in range(2):
        box_net(pdf, MARGIN + 2 + k * (2 * 10 + g.CUSHION_W + 10), top - hc, g.CUSHION_W, g.D_PANEL, 10.0, 5.0,
                'ПОДУШКА %d' % (k + 1), '%s × %s × 10' % (fmt2(g.CUSHION_W), fmt(g.D_PANEL)))
    hb = 2 * 4.8 + 2 * g.D_PANEL + 4
    by = top - hc - 8 - hb
    box_net(pdf, MARGIN + 2, by, g.W_IN, g.D_PANEL, 4.8, 4.0, 'ОСНОВАНИЕ', '%s × %s × 4,8' % (fmt(g.W_IN), fmt(g.D_PANEL)))
    # пламя
    fl = flame_outline()
    minx = min(p[0] for p in fl)
    minz = min(p[1] for p in fl)
    fx, fy = MARGIN + 2 + g.W_IN + 2 * 4.8 + 10, by + 6
    P = [(fx + p[0] - minx, fy + p[1] - minz) for p in fl]
    pdf.poly(P, w=0.3)
    # линия контура спинки на «пламени» (до неё клей)
    prof = [(12, g.H_HI), (g.X_HI_END, g.H_HI), (g.X_LO_START, g.H_LO), (76, g.H_LO)]
    pdf.poly([(fx + p[0] - minx, fy + p[1] - minz) for p in prof], close=False, w=0.2, d=[0.8, 0.8],
             col=(0.4, 0.4, 0.4))
    pdf.text(fx + 30, fy + 3, 'клей ниже пунктира', size=2.0, anchor='c', col=(0.3, 0.3, 0.3))
    pdf.text(fx, fy - 4.5, '«ПЛАМЯ» — по желанию (есть только на фото)', size=2.4, bold=True)
    pdf.text(fx, fy - 8, 'клеить к задней грани спинки', size=2.2)
    footer(pdf)


def page_original(pdf, skp_path):
    import load  # noqa: WPS433
    pc, pt = load.load(skp_path)
    IN = 25.4
    X0, Y0 = 5630.956869568563, 4046.1334088596086

    def P(v):
        return (v[0] * IN - X0, v[1] * IN - Y0)
    for o in pt.objs.values():
        if o['cls'] == 'CEdge':
            a, b = P(o['v1']['p']), P(o['v2']['p'])
            if a[0] < 1 and b[0] < 1 or a[1] < 1 and b[1] < 1 or a[0] > 209 and b[0] > 209 or a[1] > 296 and b[1] > 296:
                continue  # кромка листа (в принтер не влезет)
            pdf.line(a, b, w=0.22)
    red = (0.6, 0.05, 0.05)
    for o in pt.objs.values():
        if o['cls'] == 'CDimensionLinear':
            e = o['ends']
            A = P(e[0]['ref']['p']) if e[0]['ref'] else P(e[0]['pt'])
            B = P(e[1]['ref']['p']) if e[1]['ref'] else P(e[1]['pt'])
            off = o['off'] * IN
            if o['flag'] == 1:
                y = A[1] + off
                pdf.dim(A, B, y - (max(A[1], B[1]) if y > A[1] else min(A[1], B[1])), kind='h', col=red, size=2.3)
            elif o['flag'] == 2:
                x = A[0] - off * o['v2'][0]
                pdf.dim(A, B, x - (max(A[0], B[0]) if x > A[0] else min(A[0], B[0])), kind='v', col=red, size=2.3)
            else:
                dx, dy = B[0] - A[0], B[1] - A[1]
                n = math.hypot(dx, dy)
                vz = o['v1'][2]
                px, py = -vz * dy / n, vz * dx / n   # v1 × dir
                # pdf.dim(kind='a') смещает по (-dy, dx)
                sgn = 1 if (px * -dy + py * dx) > 0 else -1
                pdf.dim(A, B, sgn * off, kind='a', col=red, size=2.3)
        elif o['cls'] == 'CDimensionRadial':
            arc = o['arc']
            if arc['cls'] == 'CEdge':
                arc = arc['curve']
            C = P(arc['center'])
            xa, ya = arc['xaxis'], arc['yaxis']
            r = math.hypot(*xa[:2]) * IN
            am = (arc['a0'] + arc['a1']) / 2
            Q = (C[0] + (math.cos(am) * xa[0] + math.sin(am) * ya[0]) * IN,
                 C[1] + (math.cos(am) * xa[1] + math.sin(am) * ya[1]) * IN)
            pdf.line(C, Q, w=0.12, col=red)
            pdf.arrow(Q, (Q[0] - C[0], Q[1] - C[1]), col=red)
            pdf.text(Q[0] + 1.5, Q[1] - 3, 'R' + fmt(r), size=2.3, col=red)
    blue = (0.1, 0.3, 0.75)
    pdf.text(8, 290, 'Исходный чертёж из файла «чертеж.skp» — лист А4, масштаб 1:1', size=3.4, bold=True, col=blue)
    pdf.text(8, 285.5, 'Синим — мои подписи видов. Внешняя рамка листа не печатается.', size=2.4, col=blue)
    pdf.text(150, 268, 'вид сбоку (повёрнут)', size=2.6, col=blue, anchor='c')
    pdf.text(47, 240, 'вид сверху (повёрнут)', size=2.6, col=blue, anchor='c')
    pdf.text(135, 168, 'вид спереди (повёрнут)', size=2.6, col=blue, anchor='c')


def build(out_pdf, skp_path, iso_png):
    pdf = Pdf(out_pdf)
    page_instructions(pdf, iso_png)
    pdf.new_page(landscape=True)
    page_views(pdf)
    pdf.new_page(landscape=False)
    page_back(pdf)
    pdf.new_page()
    page_panels(pdf)
    pdf.new_page()
    page_seat(pdf)
    pdf.new_page()
    page_original(pdf, skp_path)
    pdf.save()


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
