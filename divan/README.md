# Диванчик — макет по чертежу `чертеж.skp`

- `divan_maket.pdf` — инструкция, итоговый чертёж 1:1, выкройки 1:1 (стр. 3–5, печатать 100 %), исходный чертёж из файла.
- `preview_3d.png` — как выглядит собранная модель.
- `tools/` — разбор файла SketchUp 2019 (`skp.py`, `load.py`), геометрия (`geom.py`) и сборка PDF (`make_pdf.py`).

Пересобрать: `python3 tools/render3d.py iso1.png preview_3d.png && python3 tools/make_pdf.py divan_maket.pdf путь/к/чертеж.skp preview_3d.png`
(нужны `reportlab` и `matplotlib`; смещения в `load.py` подобраны под этот конкретный файл).
