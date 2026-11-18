export const today = '2026-10-24';
export const operators = ['Алексей Смирнов', 'Мария Орлова', 'Иван Волков'];
export const stages = ['Выявлены непереданные документы', 'Первый звонок', 'Ожидание срока', 'Повторная проверка', 'Претензия', 'Работа завершена'];
export const dynamics = ['Нет сравнения', 'Нет данных', 'Все переданы', 'Впервые', 'Уменьшается', 'Без улучшения', 'Вернулся'];
export const clientTags = ['Новичок', 'Хронический', 'Не работать', 'Претензия'];
export const dateText = (date) => date ? date.slice(0, 10).split('-').reverse().join('.') : '—';
export const dateStatus = (date) => !date ? '' : date < today ? 'Просрочен' : date === today ? 'Сегодня' : 'Не наступил';

const rows = [
  ['Альфа', 2, 30, 3, 0, 1, '09-30'], ['Бета', 1, 25, 2, 1, 1, '09-25'],
  ['Гамма', 1, 10, 2, 0, 3, '10-15', ['Новичок', 'Хронический']],
  ['Дельта', 3, 14, 3, 2, 3, '10-01', ['Хронический']],
  ['Эпсилон', 5, 26, 6, 1, 4, '', ['Претензия']],
  ['Зета', 0, 100, 2], ['Эта', 8, 50, 9, 2, 3, '', ['Не работать']],
  ['Тета', 0, 12, 0, 0, 5], ['Йота', 1, 20, 2, 2, 1, '09-30'],
  ['Каппа', 4, 25, 5, 0, 2, '10-31'], ['Лямбда', 7, 10, 6],
  ['Мю', 0, 0, 0, 1, 5], ['Ню', 4, 20, null, 1, 1, '04-30'],
  ['Кси', 5, 100, 4], ['Омикрон', 0, 0, 0],
  ['Пи', 3, 12, null, null, 0, '', ['Новичок']],
  ['Ро', 6, 20, null, 1, 2, '10-25'], ['Сигма', 1, 40, null],
  ['Тау', 8, 16, null], ['Ипсилон', 4, 10, null, 2, 2, '10-22'],
];
const previousTotals = [25, 20, 8, 12, 22, 100, 50, 12, 20, 20, 9, 10, null, 100, 0];

function trend(missing, total, history) {
  if (!total) return 'Нет данных';
  if (!missing) return 'Все переданы';
  const previous = history.find((snapshot) => snapshot.total > 0);
  if (!previous) return 'Впервые';
  if (!previous.missing) return history.some((snapshot) => snapshot.missing > 0) ? 'Вернулся' : 'Впервые';
  return missing < previous.missing ? 'Уменьшается' : 'Без улучшения';
}

export function initialData() {
  return {
    batches: [],
    clients: rows.map(([name, missing, total, previous, owner, stage = 0, deadline, tags = []], index) => {
      const prior = previous === null ? [] : [{ date: '2026-08-17', missing: previous, total: previousTotals[index], trend: 'Нет сравнения' }];
      const due = deadline ? '2026-' + deadline : '';
      return {
        id: String(1000001 + index), inn: String(9900000001 + index), name: 'ООО «' + name + '-Тест»',
        owner: operators[owner] ?? '', stage: stages[stage], tags, due,
        queued: [0, 2, 3, 8, 9, 10, 13, 15, 16, 18, 19].includes(index),
        next: index === 10 ? today : index === 15 ? '2026-10-26' : due,
        snapshots: [{ date: '2026-10-20', missing, total, trend: index === 12 || index === 16 || index === 19 ? 'Вернулся' : trend(missing, total, prior) }, ...prior],
        calls: due ? [{ id: 'initial-' + index, date: index === 16 ? '2026-10-01' : index === 19 ? '2026-10-18' : index === 12 ? '2026-04-10' : '2026-09-05', recordedAt: '', author: operators[owner], result: 'Дозвонились', agreement: 'Передать оставшиеся документы', due }] : [],
        claims: index === 4 ? [{ number: 'П-014', date: '2026-09-25', status: 'Получена клиентом', sanction: '' }] : [],
      };
    }),
  };
}

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
  Number(b.next !== '' && b.next < today) - Number(a.next !== '' && a.next < today)
  || Number(b.tags.includes('Хронический')) - Number(a.tags.includes('Хронический'))
  || b.snapshots[0].missing - a.snapshots[0].missing);

export function saveCall(data, id, form, author) {
  const now = new Date();
  const call = { ...form, id: crypto.randomUUID(), author, date: form.backdated ? form.date : today,
    recordedAt: now.toISOString(), time: now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) };
  return { ...data, clients: data.clients.map((client) => client.id !== id ? client : {
    ...client, calls: [call, ...client.calls].sort((a, b) => b.date.localeCompare(a.date) || b.recordedAt.localeCompare(a.recordedAt)),
    due: form.due, next: form.next, stage: form.stage,
  }) };
}

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

export function applyImport(data, report, meta) {
  if (report.duplicates || !report.accepted.length) throw new Error('Нет строк, которые можно импортировать.');
  if (data.batches.some((batch) => batch.digest === meta.digest || batch.date === meta.date)) {
    throw new Error('Этот файл или срез на указанную дату уже загружен.');
  }
  const updates = new Map(report.accepted.map((row) => [row.id, row]));
  return {
    batches: [{ ...meta, accepted: report.accepted.length, errors: report.errors.length }, ...data.batches],
    clients: data.clients.map((client) => {
      const row = updates.get(client.id);
      if (!row) return client;
      const history = client.snapshots.filter((snapshot) => snapshot.date < meta.date);
      const snapshot = { date: meta.date, missing: row.missing, total: row.total, trend: trend(row.missing, row.total, history) };
      return { ...client, snapshots: [snapshot, ...client.snapshots].sort((a, b) => b.date.localeCompare(a.date)) };
    }),
  };
}
