"""Согласованная геометрия диванчика (мм).

X — по длине дивана (0 = наружная грань левой боковины, если смотреть спереди),
Y — по глубине (0 = перед), Z — высота (0 = пол).
Источник размеров: вид спереди (ширины/высоты) + вид сбоку (глубина, профиль боковины).
"""
import math

# --- вид спереди ---
T_L = 10.5          # толщина левой боковины
T_R = 10.4          # толщина правой боковины
W_IN = 85.3         # между боковинами
W = T_L + W_IN + T_R  # 106.2
H_HI = 87.7         # высокая часть спинки = высота левой боковины
H_LO = 66.0         # низкая часть спинки = высота правой боковины
X_HI_END = 55.4     # высокая часть от левого края (с боковиной)
X_LO_START = 72.2   # начало низкой части (55.4 + 16.8)
Z_BASE0 = 12.9      # низ основания сиденья
Z_BASE1 = 17.7      # верх основания (4.8)
Z_SEAT = 27.7       # верх подушек (подушка 10)

# --- вид сбоку ---
D_SLAB = 10.0       # толщина спинки
D_PANEL = 50.5      # глубина боковины перед спинкой
D = D_PANEL + D_SLAB  # 60.5
LEG_D = 9.4         # глубина переднего «ножки»
Z_UNDER = 7.5       # высота просвета под боковиной
Z_FRONT = 22.93     # высота передней грани боковины
ARC_C = (34.19, 1.22)  # центр дуги (Y, Z)
ARC_R = 40.5
ARC_END = (24.42, 40.52)  # точка излома (конец дуги)


def back_outline():
    """Контур спинки (X, Z), вид спереди, против часовой."""
    return [(0, 0), (W, 0), (W, H_LO), (X_LO_START, H_LO), (X_HI_END, H_HI), (0, H_HI)]


def arc_points(n=24):
    """Точки дуги от верха передней грани (0, Z_FRONT) до излома."""
    cy, cz = ARC_C
    a0 = math.atan2(Z_FRONT - cz, 0 - cy)
    a1 = math.atan2(ARC_END[1] - cz, ARC_END[0] - cy)
    return [(cy + ARC_R * math.cos(a0 + (a1 - a0) * i / n),
             cz + ARC_R * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def arc_length():
    cy, cz = ARC_C
    a0 = math.atan2(Z_FRONT - cz, 0 - cy)
    a1 = math.atan2(ARC_END[1] - cz, ARC_END[0] - cy)
    return ARC_R * abs(a1 - a0)


def panel_outline(h_back, n=24):
    """Профиль боковины (Y, Z): против часовой, начиная с переднего нижнего угла."""
    pts = [(0, 0), (LEG_D, 0), (LEG_D, Z_UNDER), (D_PANEL, Z_UNDER), (D_PANEL, h_back)]
    pts += list(reversed(arc_points(n)))  # от излома к передней грани
    return pts


def panel_segments(h_back):
    """Отрезки ленты боковины (название, длина, тип) — по периметру, начиная спереди снизу вверх."""
    slope = math.hypot(D_PANEL - ARC_END[0], h_back - ARC_END[1])
    return [
        ('перед', Z_FRONT, 'line'),
        ('дуга R40,5', arc_length(), 'arc'),
        ('скос', slope, 'line'),
        ('зад (к спинке)', h_back - Z_UNDER, 'line'),
        ('низ', D_PANEL - LEG_D, 'line'),
        ('ножка', Z_UNDER, 'line'),
        ('низ ножки', LEG_D, 'line'),
    ]


def back_segments():
    o = back_outline()
    names = ['низ', 'правый торец', 'верх низкой части', 'скос', 'верх высокой части', 'левый торец']
    segs = []
    for i, nm in enumerate(names):
        a, b = o[i], o[(i + 1) % len(o)]
        segs.append((nm, math.hypot(b[0] - a[0], b[1] - a[1]), 'line'))
    return segs


def interior_angles(poly):
    """Внутренние углы многоугольника (против часовой), градусы."""
    n = len(poly)
    res = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        a = math.atan2(p0[1] - p1[1], p0[0] - p1[0])
        b = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        ang = math.degrees(a - b) % 360
        res.append(ang)
    return res


CUSHION_W = W_IN / 2  # 42.65
