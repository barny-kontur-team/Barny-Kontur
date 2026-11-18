"""Прогон 30 контрольных вопросов H-03 / H-05 по выбранным моделям.

Что делает:
  * загружает тестовый набор h02 (клиенты, 6 срезов) и фикстуру звонков;
  * блок А — сводка по клиенту (функция 1);
  * блок Б — запрос словами: модель подбирает фильтр, клиентов отбирает код (функция 2);
  * блок В — вопросы «нет данных» (та же функция 1);
  * складывает ответы, фильтры и автопроверку в scripts/h03/out/.

Запуск:
  python scripts/h03/run_questions.py --check-data
  python scripts/h03/run_questions.py --models deepseek-flash,qwen3.5:2b,gemma4:e2b
  python scripts/h03/run_questions.py --models qwen3.5:2b --blocks B --limit 2
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _path in (ROOT / "backend", HERE):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import data_loader  # noqa: E402
from ai.providers import ProviderError, build_provider  # noqa: E402
from ai.schemas import ClientFilter, apply_filter  # noqa: E402
from ai.search import search_clients  # noqa: E402
from ai.summary import build_facts, summarize_client  # noqa: E402

QUESTIONS = HERE / "questions.json"
DEFAULT_MODELS = "deepseek-flash,qwen3.5:2b,gemma4:e2b"
TODAY = date(2026, 11, 1)

NO_DATA_MARKERS = ("нет данных", "нет информации", "не содержится", "отсутствуют",
                   "не известн", "неизвестн")
BAD_PATTERNS = (
    ("e-mail", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("телефон", re.compile(r"(?:\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")),
    ("рубли", re.compile(r"\d[\d\s]*\s*(?:руб|₽|р\.)", re.IGNORECASE)),
)


def slug(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", model).strip("-")


def load_questions() -> dict:
    return json.loads(QUESTIONS.read_text(encoding="utf-8"))


# --- автопроверки -----------------------------------------------------------

def allowed_numbers(facts: dict) -> set[str]:
    """Все числа, которые есть в фактах, включая варианты округления."""
    raw = json.dumps(facts, ensure_ascii=False)
    allowed: set[str] = set()
    for token in re.findall(r"\d+(?:[.,]\d+)?", raw):
        token = token.replace(",", ".")
        allowed.add(token)
        allowed.add(token.replace(".", ","))
        try:
            value = float(token)
        except ValueError:
            continue
        allowed.add(str(int(value)))
        allowed.add(f"{value:.1f}")
        allowed.add(f"{value:.1f}".replace(".", ","))
        allowed.add(f"{round(value):d}")
    return allowed


DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b")


def suspicious_numbers(answer: str, facts: dict) -> list[str]:
    """Числа из ответа, которых нет в фактах. Кандидаты в факт-ошибки.

    Даты вырезаем целиком: «12.05.2026» — это не число-факт, а дата, её
    сверяет человек. Иначе формат dd.mm.yyyy даёт ложные срабатывания.
    """
    allowed = allowed_numbers(facts)
    cleaned = DATE_RE.sub(" ", answer)
    found = {m.replace(",", ".") for m in re.findall(r"\d+(?:[.,]\d+)?", cleaned)}
    bad = []
    for number in found:
        if number in allowed or number.replace(".", ",") in allowed:
            continue
        bad.append(number)
    return sorted(bad, key=lambda x: (len(x), x))


def check_no_data(answer: str) -> dict:
    lowered = answer.lower()
    has_marker = any(marker in lowered for marker in NO_DATA_MARKERS)
    invented = [name for name, pattern in BAD_PATTERNS if pattern.search(answer)]
    return {
        "status": "ok" if has_marker and not invented else "fail",
        "has_no_data_marker": has_marker,
        "invented": invented,
    }


def question_text(questions: dict, block: str, item: dict) -> str:
    if block == "A":
        return questions["summary_template"].format(org=item["org"], code=item["code"])
    return item["question"]


# --- прогон одной модели ----------------------------------------------------

def run_model(model: str, blocks: list[str], clients: list, questions: dict,
              out_root: Path, limit: int | None) -> dict:
    provider = build_provider(model)
    model_dir = out_root / slug(model)
    model_dir.mkdir(parents=True, exist_ok=True)
    answers_path = model_dir / "answers.jsonl"
    answers_path.write_text("", encoding="utf-8")

    by_code = {c.code: c for c in clients}
    conventions = questions.get("conventions", [])
    records: list[dict] = []

    for block in blocks:
        items = questions["blocks"][block]
        if limit:
            items = items[:limit]
        for item in items:
            started = time.perf_counter()
            text = question_text(questions, block, item)
            record: dict = {
                "model": provider.name,
                "block": block,
                "id": item["id"],
                "question": text,
                "expected": item.get("expected") if block == "B" else item.get("etalon"),
            }
            try:
                if block == "B":
                    found, plan = search_clients(
                        clients, text, provider, today=TODAY,
                        context="\n".join(f"- {line}" for line in conventions) or None,
                    )
                    codes = [c.code for c in found]
                    expected = set(item.get("expected") or [])
                    record.update({
                        "answer": ", ".join(codes) if codes else "— пусто —",
                        "filter": plan.filter.describe() if plan.filter else None,
                        "filter_explanation": plan.explanation,
                        "codes": codes,
                        "auto": "ok" if set(codes) == expected else "fail",
                    })
                else:
                    client = by_code[item["code"]]
                    answer = summarize_client(client, text, provider)
                    facts = build_facts(client)
                    record["answer"] = answer
                    last = client.last
                    if last is not None:
                        record["last_slice"] = {
                            "slice_id": last.slice_id,
                            "missing": last.missing,
                            "total": last.total,
                            "share": None if last.share is None else round(last.share, 2),
                            "category": last.category,
                            "in_pool": last.in_pool,
                        }
                    if block == "C":
                        check = check_no_data(answer)
                        record.update({"auto": check["status"], "check": check})
                    else:
                        bad = suspicious_numbers(answer, facts)
                        record.update({
                            "auto": "manual",
                            "suspicious_numbers": bad,
                            "note": "полноту и факты проверяет человек по чек-листу 2.2",
                        })
            except ProviderError as exc:
                record.update({"auto": "error", "error": str(exc), "answer": ""})
            record["seconds"] = round(time.perf_counter() - started, 2)

            records.append(record)
            with answers_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

            mark = {"ok": "OK", "fail": "FAIL", "manual": "…", "error": "ERR"}[record["auto"]]
            print(f"[{provider.name}] {record['id']}: {mark} ({record['seconds']}s)", flush=True)

    report_path = model_dir / "report.md"
    report_path.write_text(render_report(provider.name, records), encoding="utf-8")
    return {
        "model": provider.name,
        "records": records,
        "report": report_path,
    }


# --- отчёты -----------------------------------------------------------------

def render_report(model: str, records: list[dict]) -> str:
    lines = [f"# H-03 / H-05: прогон модели {model}", "",
             f"Дата прогона: {time.strftime('%Y-%m-%d %H:%M')}",
             f"«Сегодня» для модели: {TODAY.isoformat()}", ""]

    for block in ("A", "B", "C"):
        block_records = [r for r in records if r["block"] == block]
        if not block_records:
            continue
        lines += [f"## Блок {block}", ""]
        for record in block_records:
            lines += [f"### {record['id']} — {record['auto']}", "",
                      f"**Вопрос:** {record['question']}", ""]
            if block == "B":
                lines += [f"**Условия фильтра:** {record.get('filter') or '—'}",
                          f"**Объяснение модели:** {record.get('filter_explanation') or '—'}",
                          f"**Коды (отобрал код):** {record.get('codes')}",
                          f"**Эталон:** {record.get('expected')}", ""]
            else:
                last = record.get("last_slice")
                if last:
                    share = "—" if last["share"] is None else f"{last['share']}%"
                    lines += [
                        f"**Последний срез (для сверки):** {last['slice_id']}, "
                        f"{last['missing']}/{last['total']}, {share}, "
                        f"«{last['category']}», {'в пуле' if last['in_pool'] else 'вне пула'}",
                        "",
                    ]
                if record.get("suspicious_numbers"):
                    lines += [f"**Числа вне фактов (проверить):** {record['suspicious_numbers']}", ""]
                if record.get("check"):
                    lines += [f"**Автопроверка:** {record['check']}", ""]
                lines += [f"**Эталон:** {record.get('expected')}", ""]
                lines += ["**Ответ модели:**", "", "```", record.get("answer") or "", "```", ""]
            if record.get("error"):
                lines += [f"**Ошибка:** {record['error']}", ""]
    return "\n".join(lines)


def render_summary(results: list[dict]) -> str:
    lines = ["# Сводка прогона H-03 / H-05", "",
             f"Дата: {time.strftime('%Y-%m-%d %H:%M')}", "",
             "| Модель | Блок Б: совпало | Блок В: «нет данных» | Блок А: предупреждения |",
             "|---|---|---|---|"]
    for result in results:
        records = result["records"]
        b = [r for r in records if r["block"] == "B"]
        c = [r for r in records if r["block"] == "C"]
        a = [r for r in records if r["block"] == "A"]
        b_ok = sum(1 for r in b if r["auto"] == "ok")
        c_ok = sum(1 for r in c if r["auto"] == "ok")
        a_warn = sum(1 for r in a if r.get("suspicious_numbers"))
        lines.append(f"| {result['model']} | {b_ok}/{len(b)} | {c_ok}/{len(c)} | {a_warn}/{len(a)} |")
    lines += ["", "Блок А оценивает человек по чек-листу 2.2; здесь только кандидаты в факт-ошибки.", ""]
    return "\n".join(lines)


# --- вспомогательное --------------------------------------------------------

def print_data_check(clients: list) -> None:
    print(f"клиентов: {len(clients)}")
    print(f"{'код':8} {'срез':6} {'not':>4} {'total':>5} {'доля':>7} {'категория':22} "
          f"{'пул':4} {'этап'}")
    for client in clients:
        last = client.last
        if last is None:
            print(f"{client.code:8} — нет срезов")
            continue
        share = "—" if last.share is None else f"{last.share:.2f}%"
        print(f"{client.code:8} {last.slice_id:6} {last.missing:>4} {str(last.total):>5} "
              f"{share:>7} {last.category:22} {'да' if last.in_pool else 'нет':4} "
              f"{client.stage or '—'}")


def check_filters(clients: list, questions: dict) -> bool:
    """Самопроверка кода: эталонные условия должны давать эталонные коды."""
    reference = json.loads((HERE / "filters_reference.json").read_text(encoding="utf-8"))
    ok = True
    for item in questions["blocks"]["B"]:
        data = reference.get(item["id"])
        if data is None:
            continue
        flt = ClientFilter.from_dict(data)
        codes = [c.code for c in apply_filter(clients, flt)]
        expected = sorted(item["expected"])
        status = "OK" if codes == expected else "FAIL"
        ok = ok and codes == expected
        print(f"{item['id']}: {status} got={codes} expected={expected}")
    return ok


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — консоль без UTF-8 не должна ломать прогон
        pass

    parser = argparse.ArgumentParser(description="Прогон 30 вопросов H-03/H-05")
    parser.add_argument("--models", default=DEFAULT_MODELS,
                        help=f"через запятую (по умолчанию {DEFAULT_MODELS})")
    parser.add_argument("--blocks", default="A,B,C", help="какие блоки гнать: A,B,C")
    parser.add_argument("--out", default=str(HERE / "out"), help="куда писать результаты")
    parser.add_argument("--limit", type=int, default=None, help="по N вопросов на блок")
    parser.add_argument("--check-data", action="store_true",
                        help="только проверить загрузку данных, без вызова моделей")
    parser.add_argument("--check-filters", action="store_true",
                        help="самопроверка: эталонные условия дают эталонные коды")
    args = parser.parse_args()

    questions = load_questions()
    clients = data_loader.load_clients()

    if args.check_data:
        print_data_check(clients)
        return

    if args.check_filters:
        ok = check_filters(clients, questions)
        raise SystemExit(0 if ok else 1)

    blocks = [b.strip().upper() for b in args.blocks.split(",") if b.strip()]
    for block in blocks:
        if block not in questions["blocks"]:
            parser.error(f"неизвестный блок: {block}")

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    results = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        results.append(run_model(model, blocks, clients, questions, out_root, args.limit))

    summary = render_summary(results)
    (out_root / "summary.md").write_text(summary, encoding="utf-8")
    (out_root / "summary.json").write_text(
        json.dumps([{"model": r["model"], "records": r["records"]} for r in results],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n" + summary)
    print(f"Результаты: {out_root}")


if __name__ == "__main__":
    main()
