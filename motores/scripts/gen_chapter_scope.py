"""Alcance capítulo/modo para apply_corrections — B2/B3/B4/B8 rápidos.

Cada motor opera en su dominio (hebreo, griego, español) de forma
independiente. No hay capítulos protegidos: todos pasan por el pipeline
completo para que cada motor pueda hacer su trabajo.
"""
from __future__ import annotations

SCOPE_CHAPTER: int | None = None
SCOPE_MODE: str = "full"

MODES = frozenset({"full", "hebrew", "lxx", "spanish"})

# Sin protección de capítulos — todos pasan por el pipeline completo.
PROTECTED_CHAPTERS: frozenset[int] = frozenset()
PROTECTED_BOOK: str = ""

LOCKED_HEBREW_FIELDS: frozenset[str] = frozenset()


def is_hebrew_locked(ch: int, book: str = "genesis") -> bool:
    """Siempre False — no hay candado, cada motor opera en su dominio."""
    return False


def set_scope(chapter: int | None, mode: str) -> None:
    global SCOPE_CHAPTER, SCOPE_MODE
    SCOPE_CHAPTER = chapter
    if chapter is None:
        SCOPE_MODE = "full"
    else:
        SCOPE_MODE = mode if mode in MODES else "hebrew"


def in_scope(ch: int) -> bool:
    return SCOPE_CHAPTER is None or SCOPE_CHAPTER == ch


def is_protected(ch: int, book: str = "genesis") -> bool:
    """True si el capítulo ya está cerrado y no debe ser tocado por reglas nuevas."""
    return book == PROTECTED_BOOK and ch in PROTECTED_CHAPTERS


def is_rules_target(ch: int, book: str = "genesis") -> bool:
    """True si el capítulo es candidato para recibir reglas nuevas."""
    return not is_protected(ch, book)


def skip_spanish_passes() -> bool:
    return SCOPE_MODE in ("hebrew", "lxx")


def skip_lxx_in_re() -> bool:
    return SCOPE_MODE == "hebrew"


def skip_ch_final() -> bool:
    return SCOPE_MODE in ("hebrew", "lxx")


def skip_pass17() -> bool:
    return skip_spanish_passes()


def scope_label() -> str:
    if SCOPE_CHAPTER is None:
        return "libro completo · mode=full"
    return f"cap. {SCOPE_CHAPTER} · mode={SCOPE_MODE}"
