"""Validation of anonymized H-02 client and snapshot workbook rows."""
from collections import Counter
from datetime import date, datetime
from io import BytesIO
from openpyxl import load_workbook

class ImportValidationError(ValueError): pass

CLIENT_REQUIRED = ("Код КЦР", "ИНН", "Название организации")
SLICE_REQUIRED = ("Код КЦР", "Документов всего", "Не передано документов")

def parse_workbook(content: bytes, kind: str, known_codes: set[str] | None = None, allow_missing_total_codes: set[str] | None = None) -> list[dict]:
    try: wb = load_workbook(BytesIO(content), data_only=True, read_only=True)
    except Exception as e: raise ImportValidationError(f"Некорректный Excel-файл: {e}") from e
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    head = next(rows, None)
    if not head: raise ImportValidationError("Пустой Excel-файл")
    header = [str(v).strip() if v is not None else "" for v in head]
    req = CLIENT_REQUIRED if kind == "clients" else SLICE_REQUIRED
    missing = [x for x in req if x not in header]
    if missing: raise ImportValidationError("Отсутствуют обязательные столбцы: " + ", ".join(missing))
    indices = {k: header.index(k) for k in header if k}
    parsed=[]; errors=[]
    for row_num, values in enumerate(rows, 2):
        if not any(x is not None and str(x).strip() for x in values): continue
        record = {k: values[i] if i<len(values) else None for k,i in indices.items()}
        code = str(record.get("Код КЦР") or "").strip()
        record["Код КЦР"] = code
        if not code: errors.append(f"Строка {row_num}: пустой код КЦР");continue
        if kind == "clients":
            for k in CLIENT_REQUIRED[1:]:
                if record.get(k) is None or not str(record[k]).strip(): errors.append(f"Строка {row_num}: пустое поле «{k}»")
        else:
            for k in SLICE_REQUIRED[1:]:
                v=record.get(k)
                if v is None or str(v).strip()=="":
                    if k == "Документов всего" and code in (allow_missing_total_codes or set()): continue
                    errors.append(f"Строка {row_num}: пустое поле «{k}»");continue
                if isinstance(v,bool) or not isinstance(v,(int,float)) or int(v)!=v or v<0:
                    errors.append(f"Строка {row_num}: «{k}» должно быть целым неотрицательным числом")
            total=record.get("Документов всего"); missing_count=record.get("Не передано документов")
            if isinstance(total,(int,float)) and isinstance(missing_count,(int,float)) and missing_count>total:
                errors.append(f"Строка {row_num}: непереданных документов больше общего количества")
            if known_codes is not None and code not in known_codes:
                errors.append(f"Строка {row_num}: код КЦР {code} отсутствует в справочнике")
        parsed.append(record)
    counts=Counter(r["Код КЦР"] for r in parsed)
    dup=[k for k,v in counts.items() if v>1]
    if dup: raise ImportValidationError("Повтор кода КЦР в одном файле: " + ", ".join(dup))
    if errors: raise ImportValidationError("; ".join(errors))
    if not parsed: raise ImportValidationError("Нет строк для импорта")
    return parsed
