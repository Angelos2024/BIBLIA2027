import sys
sys.path.insert(0, 'scripts')
sys.stdout.reconfigure(encoding='utf-8')
from parse_genesis import _clean_gr_raw, gk_beta_to_unicode

raw = r"KATA\ GE/NOS {d} KAI\ KAQ' O(MOIO/THTA"
cleaned = _clean_gr_raw(raw)
print('cleaned:', repr(cleaned))
result = gk_beta_to_unicode(cleaned)
print('unicode:', result)
