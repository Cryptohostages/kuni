import re
from datetime import time

_NAME = re.compile(r"^[A-Za-zА-Яа-яЁё]+(?:[ '’-][A-Za-zА-Яа-яЁё]+)*$")
_CLASS = re.compile(r"^(1[01]|[1-9])(?!\d)\s*[-–—]?\s*([а-яёa-z]{0,2})\s*[-–—]?\s*(\d{0,2})$")
_QUOTES = re.compile(r"[«»\"'“”„]")
_CLASS_WORD = re.compile(r"\bкл(?:асс|\.)?\b|-?(?:й|ый|ой)\b")
_TIME = re.compile(r"^([01]?\d|2[0-3])[:.\- ]?([0-5]\d)$")

ROLES = {
    "родитель": "родитель",
    "родители": "родитель",
    "мама": "родитель",
    "папа": "родитель",
    "учитель": "учитель",
    "учительница": "учитель",
    "педагог": "учитель",
    "классный руководитель": "учитель",
}


def normalize_name(raw: str) -> str | None:
    name = " ".join(raw.split())
    if not 2 <= len(name) <= 60 or not _NAME.match(name):
        return None
    if name == name.lower() or name == name.upper():
        name = name.title()
    return name


def normalize_class(raw: str) -> str | None:
    text = " ".join(raw.lower().split()).strip(" .")
    if text in ROLES:
        return ROLES[text]
    text = _QUOTES.sub("", _CLASS_WORD.sub("", text)).strip(" .")
    match = _CLASS.match(text)
    if not match:
        return None
    number, letters, index = match.groups()
    if letters:
        return f"{number}{letters.upper()}{index}"
    if index:
        return f"{number}-{index}"
    return number


def parse_time(raw: str) -> time | None:
    match = _TIME.match(raw.strip())
    if not match:
        return None
    return time(int(match.group(1)), int(match.group(2)))
