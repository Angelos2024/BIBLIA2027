"""Remove stray diaeresis (U+0308) and leading '...' from Greek fields."""
import sys, json, re, argparse, unicodedata
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from book_config import resolve

_DIAERESIS = '\u0308'
_DOTS = re.compile(r'\.{2,3}\s*')
_MULTI_DASH = re.compile(r"-{2,}\s*")
_EMPTY_QUOTES = re.compile(r"''\s*")
_STRAY_DOT = re.compile(r'(?<!\w)\.\s*$')
_STRAY_BRACES = re.compile(r'[{}]')
_MULTI_SPACE = re.compile(r'  +')


def clean(text: str) -> str:
    if not text or text == '----':
        return text
    out = text.replace(_DIAERESIS, '')
    out = _DOTS.sub('', out)
    out = _EMPTY_QUOTES.sub('', out)
    out = _MULTI_DASH.sub('', out)
    out = _STRAY_DOT.sub('', out)
    out = _STRAY_BRACES.sub('', out)
    out = _MULTI_SPACE.sub(' ', out).strip()
    return out


def process_book(cfg, dry_run: bool):
    data = json.loads(cfg.final_json_path.read_text(encoding='utf-8'))
    stats = {'gr_unicode': 0, 'gr_word': 0, 'prefix_gr': 0, 'prs_gr': 0}

    for v in data['verses']:
        for p in v.get('pairs', []):
            # pair-level gr_unicode
            old = p.get('gr_unicode') or ''
            new = clean(old)
            if new != old:
                stats['gr_unicode'] += 1
                if not dry_run:
                    p['gr_unicode'] = new

            for hw in p.get('he_words', []):
                # gr_word
                old = hw.get('gr_word') or ''
                new = clean(old)
                if new != old:
                    stats['gr_word'] += 1
                    if not dry_run:
                        hw['gr_word'] = new

                # prefix_gr
                pgr = hw.get('prefix_gr') or []
                for i, pg in enumerate(pgr):
                    if not pg:
                        continue
                    new = clean(pg)
                    if new != pg:
                        stats['prefix_gr'] += 1
                        if not dry_run:
                            pgr[i] = new

                # prs_suffix.gr_word
                prs = hw.get('prs_suffix') or {}
                old = prs.get('gr_word') or ''
                new = clean(old)
                if new != old:
                    stats['prs_gr'] += 1
                    if not dry_run:
                        prs['gr_word'] = new

    return data, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('book')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    cfg = resolve(args.book)
    mode = 'APPLY' if args.apply else 'DRY-RUN'
    print(f'Clean Greek artifacts: {cfg.label} ({mode})')
    print('=' * 60)

    data, stats = process_book(cfg, dry_run=not args.apply)

    total = sum(stats.values())
    for k, v in sorted(stats.items()):
        print(f'  {k:20s} {v:>6d}')
    print(f'  {"TOTAL":20s} {total:>6d}')

    if args.apply and total > 0:
        cfg.final_json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
        )
        print(f'\nGuardado: {cfg.final_json_path}')
    elif not args.apply:
        print('\n(dry-run, usa --apply para guardar)')


if __name__ == '__main__':
    main()
