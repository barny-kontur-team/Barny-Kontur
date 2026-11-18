"""Negative cases E01-E12; nonzero exit when any malformed file is accepted."""
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'backend'))
from importer.validation import parse_workbook,ImportValidationError
base=root/'data/test/h02/02_Ошибочные_импорты'
known={'1000001'}
failures=[]
lines=['# Негативные сценарии H-02/H-01','', '| Файл | Результат | Причина |','|---|---|---|']
for path in sorted(base.glob('*.xlsx')):
    kind='clients' if 'Клиенты' in path.name else 'snapshots'
    try:
        parse_workbook(path.read_bytes(),kind,known if kind=='snapshots' else None)
    except ImportValidationError as e:
        reason=str(e)
        print(f'{path.name}: ОТКЛОНЁН — {reason}')
        lines.append(f'| {path.name} | ОТКЛОНЁН | {reason.replace("|","/")} |')
    else:
        failures.append(path.name);print(f'{path.name}: ОШИБКА — файл принят')
        lines.append(f'| {path.name} | НЕОЖИДАННО ПРИНЯТ | — |')
(root/'docs/H-02-negative-checklist.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
if failures: print('НЕ ПРОЙДЕНО:', failures);sys.exit(1)
print('OK:',len(lines)-4,'отрицательных файлов отклонены')
