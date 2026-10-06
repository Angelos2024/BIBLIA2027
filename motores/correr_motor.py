# -*- coding: utf-8 -*-
"""Lanzador interactivo del motor de español (revisar_es.py).

Corre el motor sobre el libro/capítulo que elijas, SIN depender del asistente.
Uso normal: doble clic en Correr_Motor.bat (raíz del proyecto), o:

    python motores/correr_motor.py                 (interactivo)
    python motores/correr_motor.py genesis 24       (informe cap 24)
    python motores/correr_motor.py genesis 24 apply  (aplica arreglos seguros)

Aplica SOLO arreglos seguros (CANON · PENINSULAR · CONSTRUCT) con respaldo, y
NUNCA toca capítulos cerrados (candado). El resto son solo informe.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'data_master'
SCRIPT = REPO / 'motores' / 'scripts' / 'revisar_es.py'


def _run(book, chapter, apply):
    cmd = [sys.executable, str(SCRIPT), '--book', book]
    if chapter:
        cmd += ['--chapter', str(chapter)]
    if apply:
        cmd.append('--apply')
    return subprocess.run(cmd, cwd=str(REPO)).returncode


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    books = sorted(p.name[:-len('_final.json')] for p in DATA.glob('*_final.json'))
    args = sys.argv[1:]

    if args:                       # modo directo (CLI)
        book = args[0]
        chapter = args[1] if len(args) > 1 and args[1].isdigit() else ''
        apply = 'apply' in (a.lower() for a in args)
        if apply and chapter:      # informe primero, luego aplicar
            _run(book, chapter, False)
        return _run(book, chapter, apply)

    # modo interactivo
    print('═══ MOTOR DE ESPAÑOL (revisar_es) ═══')
    print('Libros disponibles:', ', '.join(books) or '(ninguno)')
    book = input('\nLibro [genesis]: ').strip() or 'genesis'
    if book not in books:
        print(f'No existe {book}_final.json. Cancelado.')
        return 1
    chapter = input('Capítulo (número; Enter = libro completo): ').strip()
    if chapter and not chapter.isdigit():
        print('El capítulo debe ser un número. Cancelado.')
        return 1

    print(f'\n── INFORME (nada se modifica) · {book} '
          f'{chapter or "(completo)"} ──\n')
    _run(book, chapter, False)

    resp = input('\n¿Aplicar arreglos SEGUROS (CANON · PENINSULAR · CONSTRUCT)? '
                 '[s/N]: ').strip().lower()
    if resp in ('s', 'si', 'sí', 'y', 'yes'):
        print()
        _run(book, chapter, True)
        print('\n✔ Listo. Si tienes el visor abierto, recarga la página '
              '(F5) para ver los cambios.')
    else:
        print('Solo informe. No se modificó nada.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
