import { useRef, useState } from 'react';
import { Badge, Button, Field, Metric, Select, Table } from './ui';
import { dateText, inspectRows } from './demo';

const periods = ['I квартал 2026', 'II квартал 2026', 'III квартал 2026', 'IV квартал 2026'];
const sampleNames = ['С ошибками строк', 'С дубликатом'];

function downloadErrors(errors) {
  const escape = (value) => {
    const cell = String(value ?? '');
    return '"' + (/^[\s]*[=+@-]/.test(cell) ? "'" : '') + cell.replaceAll('"', '""') + '"';
  };
  const csv = ['Строка;Идентификатор;Причина', ...errors.map(({ row, id, reason }) => [row, id, reason].map(escape).join(';'))].join('\r\n');
  const url = URL.createObjectURL(new Blob(['\uFEFF', csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'отчёт-ошибок.csv';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ImportScreen({ data, onImport, openClients }) {
  const [period, setPeriod] = useState(periods[3]);
  const [date, setDate] = useState('2026-11-20');
  const [source, setSource] = useState(null);
  const [report, setReport] = useState(null);
  const [meta, setMeta] = useState(null);
  const [done, setDone] = useState(false);
  const [showRows, setShowRows] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const input = useRef(null);

  function choose(file) {
    setMessage('');
    if (!file) return;
    if (!/\.xlsx$/i.test(file.name) || file.size > 10 * 1024 * 1024) {
      setMessage('Выберите файл .xlsx размером до 10 МБ.');
      setSource(null);
      return;
    }
    setSource({ file, name: file.name });
  }

  async function inspect(event) {
    event.preventDefault();
    setMessage('');
    if (!source || !date) return;
    if (data.batches.some((batch) => batch.date === date) || data.clients.some((client) => client.snapshots.some((snapshot) => snapshot.date === date))) {
      setMessage('Срез на эту дату уже существует. Укажите другую дату.');
      return;
    }
    setBusy(true);
    try {
      let rows, digest;
      if (source.file) {
        const { default: read } = await import('read-excel-file');
        rows = await read(source.file);
        const hash = await crypto.subtle.digest('SHA-256', await source.file.arrayBuffer());
        digest = Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, '0')).join('');
      } else {
        rows = [['Код КЦР', 'Всего документов', 'Не передано документов'], ['1000001', 30, 1], ['1000003', 10, 0],
          source.duplicate ? ['1000001', 30, 1] : ['9990001', 20, 3], [null, 12, 2]];
        digest = 'demo:' + source.name;
      }
      if (data.batches.some((batch) => batch.digest === digest)) throw new Error('Этот файл уже загружен.');
      setReport(inspectRows(rows, data.clients));
      setMeta({ name: source.name, date, period, digest });
    } catch (error) {
      setMessage(source.file && !/^[А-ЯЁ]/u.test(error.message) ? 'Не удалось прочитать Excel-файл. Проверьте формат и попробуйте снова.' : error.message);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setReport(null);
    setMeta(null);
    setDone(false);
    setShowRows(false);
    setMessage('');
  }

  function commit() {
    try {
      onImport(report, meta);
      setDone(true);
    } catch (error) {
      setMessage(error.message);
    }
  }

  const step = done ? 2 : report ? 1 : 0;
  const fatal = report && (report.duplicates > 0 || !report.accepted.length);
  return <>
    <nav className="tabs steps" aria-label="Шаги загрузки">{['1 Параметры', '2 Предпросмотр', '3 Результат'].map((item, index) => <span key={item} className={index === step ? 'selected' : ''} aria-current={index === step ? 'step' : undefined}>{item}</span>)}</nav>
    {message && <p className="notice red" role="alert">{message}</p>}
    {!report ? <div className="split">
      <form className="card" onSubmit={inspect}>
        <h2>Загрузить новый срез</h2>
        <Field label="Отчётный период"><Select value={period} onChange={setPeriod} options={periods} /></Field>
        <Field label="Дата среза"><input type="date" required value={date} onChange={(event) => setDate(event.target.value)} /></Field>
        <div className="field"><span>Excel-файл</span>
          <input ref={input} type="file" accept=".xlsx" hidden onChange={(event) => { choose(event.target.files[0]); event.target.value = ''; }} />
          <button type="button" className="dropzone" onClick={() => input.current.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); choose(event.dataTransfer.files[0]); }}>
            <strong>{source?.name || 'Перетащите .xlsx сюда или выберите файл'}</strong><small>До 10 МБ</small>
          </button>
        </div>
        <div className="between"><Button onClick={() => input.current.click()}>Выбрать файл</Button><Button type="submit" primary disabled={!source || busy}>{busy ? 'Проверяем…' : 'Проверить файл'}</Button></div>
      </form>
      <aside className="card stack">
        <h2>Требования к файлу</h2>
        <ul><li>Код КЦР и количество непереданных документов</li><li>Один идентификатор на строку</li><li>Дубликат отклоняет весь файл</li><li>Неизвестные строки попадут в отчёт</li></ul>
        <h3>Демонстрационные примеры</h3>
        <div className="row wrap">{sampleNames.map((name, index) => <Button key={name} onClick={() => { setMessage(''); setSource({ name, duplicate: index === 1 }); }}>{name}</Button>)}</div>
        <h3>Последние загрузки</h3>
        {data.batches.length ? data.batches.map((batch) => <div className="inset" key={batch.digest}><strong>{batch.name}</strong><div className="muted">{dateText(batch.date)} · {batch.accepted} принято</div></div>) : <div className="inset"><strong>S005 · 20.10.2026</strong><div className="muted">Исходный демонстрационный срез</div></div>}
      </aside>
    </div> : <section className="card stack">
      <div className="between">
        <div><h2>{done ? 'Импорт завершён' : fatal ? 'Файл отклонён' : showRows ? 'В файле есть ошибки' : 'Предварительный просмотр'}</h2><p>{meta.name} · {meta.period} · {dateText(meta.date)}</p></div>
        <Badge tone={done ? 'green' : fatal ? 'red' : report.errors.length ? 'amber' : 'blue'}>{done ? 'Завершено' : report.duplicates ? 'Дубликат' : report.errors.length ? 'Есть ошибки' : 'Проверено'}</Badge>
      </div>
      <div className="metrics">
        <Metric label="Строк в файле" value={report.count} />
        <Metric label={done ? 'Принято строк' : 'Готово к импорту'} value={fatal ? 0 : report.accepted.length} />
        <Metric label="Отклонено строк" value={fatal ? report.count : report.errors.length} />
      </div>
      {fatal && <p className="notice red">{report.duplicates ? 'Удалите дубликаты идентификаторов и загрузите исправленный файл. Данные не сохранены.' : 'Исправьте ошибки и загрузите файл повторно.'}</p>}
      {done && <p>Прошлые срезы и история работы с клиентами сохранены.</p>}
      {(showRows || fatal) && !done && <Table headers={['Строка', 'Идентификатор', 'Причина']} label="Ошибки импорта">
        {report.errors.map(({ row, id, reason }) => <tr key={row}><td>{row}</td><td>{id || '—'}</td><td>{reason}</td></tr>)}
      </Table>}
      <div className="between">
        <div className="row wrap">
          {!done && <Button onClick={reset}>{fatal ? 'Выбрать другой файл' : 'Назад к файлу'}</Button>}
          {report.errors.length > 0 && <Button onClick={() => downloadErrors(report.errors)}>Скачать отчёт ошибок</Button>}
        </div>
        {done ? <Button primary onClick={openClients}>Перейти к клиентам</Button> : !fatal && (report.errors.length && !showRows ?
          <Button primary onClick={() => setShowRows(true)}>Посмотреть ошибки</Button> :
          <Button primary onClick={commit}>Импортировать {report.accepted.length} строк</Button>)}
      </div>
    </section>}
  </>;
}
