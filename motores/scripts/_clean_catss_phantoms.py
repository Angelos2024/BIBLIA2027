"""Remove CATSS phantom tokens (non-Hebrew artifacts) and fill remaining gaps."""
import json, sys, re, argparse
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

CATSS_ARTIFACT = re.compile(
    r'^('
    r'<[^>]+>'        # <sp>, <q4p-agj>, <2.24>
    r'|=.+'           # =YHWH, =YQR), =%vap, =@NXH, =;HXL, =+MWNY, =W/)T
    r'|\..+'          # .bp, .)h, .x(
    r'|\*\*.+'        # **MCWT/Y, **L/N(RH (critical apparatus)
    r'|\{[^}]*\}.+'   # {!}nd, {!}p (editorial + trailing)
    r'|\{[^}]*\}'     # {...M/M/}, {..r/L)} (editorial self-contained)
    r'|--\+'          # --+ (CATSS dash-plus)
    r'|\[\d+\]'       # [15], [16], [18] (verse refs)
    r')$'
)


def is_phantom(hw):
    raw = hw.get('raw', '')
    he_form = (hw.get('he_form') or '').strip()
    if not he_form and CATSS_ARTIFACT.match(raw):
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('book', nargs='?', default='deuteronomio')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    path = Path(rf'C:\Users\pik_y\Documents\TRADUCCION\data\{args.book}_final.json')
    data = json.loads(path.read_text(encoding='utf-8'))

    phantoms_removed = 0
    pairs_removed = 0

    for v in data['verses']:
        for p in v.get('pairs', []):
            he_words = p.get('he_words', [])
            new_hws = []
            removed_any = False
            for hw in he_words:
                if is_phantom(hw):
                    phantoms_removed += 1
                    removed_any = True
                else:
                    new_hws.append(hw)
            if removed_any and args.apply:
                p['he_words'] = new_hws
                if not new_hws:
                    pairs_removed += 1

        if args.apply:
            v['pairs'] = [p for p in v.get('pairs', [])
                          if p.get('he_words') or p.get('kind') == 'gk_add']

    print(f'Clean CATSS phantoms: {args.book} ({"APPLY" if args.apply else "DRY-RUN"})')
    print('=' * 60)
    print(f'  phantom tokens removed:  {phantoms_removed}')
    print(f'  empty pairs removed:     {pairs_removed}')

    if args.apply:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=None), encoding='utf-8')
        print(f'\nGuardado: {path}')


if __name__ == '__main__':
    main()
