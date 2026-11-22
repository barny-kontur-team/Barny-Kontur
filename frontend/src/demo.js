// Справочники и правила показа. Данные клиентов теперь приходят из API,
// здесь остались только общие списки и вычисления для интерфейса.
export const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Moscow' }).format();
export const stages = ['Выявлены непереданные документы', 'Первый звонок', 'Ожидание срока', 'Повторная проверка', 'Претензия', 'Работа завершена'];
// Категории приходят из API (модель Б), поэтому фильтр использует их названия.
export const dynamics = ['Нет сравнения', 'Нет данных', 'Все переданы', 'Появился впервые', 'Уменьшается', 'Не меняется или растёт', 'Повторное появление'];
export const clientTags = ['Новичок', 'Хронический', 'Не работать', 'Претензия'];
export const dateText = (date) => date ? date.slice(0, 10).split('-').reverse().join('.') : '—';
export const dateStatus = (date) => !date ? '' : date < today ? 'Просрочен' : date === today ? 'Сегодня' : 'Не наступил';

export function canCall(client, threshold = 5) {
  const { missing, total } = client.snapshots[0];
  return total > 0 && missing > 0 && (client.tags.includes('Новичок') || missing / total * 100 >= threshold)
    && !client.tags.some((tag) => tag === 'Не работать' || tag === 'Претензия')
    && client.stage !== stages[5] && (!client.due || client.due <= today);
}

export function recommendation(client) {
  if (client.tags.includes('Не работать')) return 'Клиент исключён из обзвона.';
  if (client.tags.includes('Претензия')) return 'Проверьте состояние претензии и санкций.';
  const { missing, total } = client.snapshots[0];
  if (!total) return 'Проверьте данные последнего среза.';
  if (!missing || client.stage === stages[5]) return 'Активных действий не требуется.';
  if (client.due > today) return 'Дождитесь обещанного срока ' + dateText(client.due) + '.';
  if (!canCall(client)) return 'Проверьте данные в следующем срезе.';
  return client.calls.length ? 'Проверьте остаток и запланируйте повторный звонок.' : 'Запланируйте первый звонок.';
}

export const priorities = (clients) => clients.filter((client) => canCall(client)).sort((a, b) =>
  Number(Boolean(b.next || b.due) && (b.next || b.due) < today) -
  Number(Boolean(a.next || a.due) && (a.next || a.due) < today)
  || Number(b.tags.includes('Хронический')) - Number(a.tags.includes('Хронический'))
  || b.snapshots[0].missing - a.snapshots[0].missing);

export function inspectRows([header = [], ...rows], clients) {
  const headings = header.map((cell) => String(cell ?? '').trim().toLowerCase());
  const code = headings.findIndex((h) => ['код кцр', 'client_id', 'идентификатор'].includes(h));
  const missing = headings.findIndex((h) => ['не передано документов', 'не передано', 'not_transferred'].includes(h));
  const total = headings.findIndex((h) => ['всего документов', 'всего', 'total', 'total_ref', 'всего (только в 1-м срезе периода)'].includes(h));
  if (code < 0 || missing < 0) throw new Error('Нужны колонки «Код КЦР» и «Не передано документов».');
  const byCode = new Map(clients.map((client) => [client.id, client]));
  const seen = new Map();
  const accepted = [], errors = [];
  let duplicates = 0, count = 0;
  rows.forEach((row, index) => {
    if (row.every((cell) => cell == null || String(cell).trim() === '')) return;
    count++;
    const id = String(row[code] ?? '').trim();
    const client = byCode.get(id);
    const rowNumber = index + 2;
    const first = seen.get(id);
    const absentTotal = row[total] == null || String(row[total]).trim() === '';
    const all = absentTotal ? client?.snapshots[0].total : Number(row[total]);
    const remainder = Number(row[missing]);
    let reason = '';
    if (!id) reason = 'Пустой идентификатор';
    else if (first) {
      reason = 'Дубликат идентификатора. Первая запись — строка ' + first;
      duplicates++;
    } else if (!client) reason = 'Идентификатор отсутствует в справочнике';
    else if (row[missing] == null || String(row[missing]).trim() === '' || !Number.isSafeInteger(remainder)
      || !Number.isSafeInteger(all) || remainder < 0 || all < remainder) reason = 'Некорректное количество документов';
    if (id && !first) seen.set(id, rowNumber);
    if (reason) errors.push({ row: rowNumber, id, reason });
    else accepted.push({ id, missing: remainder, total: all });
  });
  if (!count) throw new Error('В файле нет строк для проверки.');
  return { count, accepted, errors, duplicates };
}
