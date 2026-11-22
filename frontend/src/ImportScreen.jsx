import { useRef, useState } from 'react';
import { Badge, Button, Field, Metric, Select, Table } from './ui';
import { dateText, inspectRows } from './demo';

const periods = ['I квартал 2026', 'II квартал 2026', 'III квартал 2026', 'IV квартал 2026'];
const sampleNames = ['С ошибками строк', 'С дубликатом'];
const snapshotMode = 'Срез документов';
const clientMode = 'Справочник клиентов';
const sampleClients = [{ id: '1000001' }, { id: '1000003' }];

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

export default function ImportScreen({ batches, onImport, openClients }) {
  const [mode, setMode] = useState(snapshotMode);
  const [period, setPeriod] = useState(periods[3]);
  const [date, setDate] = useState('2026-11-20');
  const [source, setSource] = useState(null);
  const [report, setReport] = useState(null);
  const [meta, setMeta] = useState(null);
  const [result, setResult] = useState(null);
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
    if (!source || (mode === snapshotMode && !date)) return;
    setBusy(true);
    try {
      if (source.file) {
        const { default: read } = await import('read-excel-file');
        const [, ...rows] = await read(source.file);
        const count = rows.filter((row) => row.some((cell) => cell != null && String(cell).trim())).length;
        setReport({ count, errors: [] });
      } else {
        const rows = [['Код КЦР', 'Всего документов', 'Не передано документов'], ['1000001', 30, 1], ['1000003', 10, 0],
          source.duplicate ? ['1000001', 30, 1] : ['9990001', 20, 3], [null, 12, 2]];
        setReport(inspectRows(rows, sampleClients));
      }
      const kind = mode === clientMode ? 'clients' : 'snapshots';
      setMeta({ name: source.name, kind, date: kind === 'snapshots' ? date : '', period: kind === 'snapshots' ? period : '' });
    } catch (error) {
      setMessage(source.file && !/^[А-ЯЁ]/u.test(error.message) ? 'Не удалось прочитать Excel-файл. Проверьте формат и попробуйте снова.' : error.message);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setReport(null);
    setMeta(null);
    setResult(null);
    setShowRows(false);
    setMessage('');
  }

  async function commit() {
    if (busy) return;
    setBusy(true);
    setMessage('');
    try {
      setResult(source.file ? await onImport(meta, source.file) : { created: report.accepted.length });
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  const done = result !== null;
  const demo = Boolean(source && !source.file);
  const step = done ? 2 : report ? 1 : 0;
  const fatal = demo && report && (report.duplicates > 0 || !report.accepted.length);
  return <>
    <nav className="tabs steps" aria-label="Шаги загрузки">{['1 Параметры', '2 Предпросмотр', '3 Результат'].map((item, index) => <span key={item} className={index === step ? 'selected' : ''} aria-current={index === step ? 'step' : undefined}>{item}</span>)}</nav>
    {message && <p className="notice red" role="alert" style={{ overflowWrap: 'anywhere' }}>{message}</p>}
    {!report ? <div className="split">
      <form className="card" onSubmit={inspect}>
        <h2>Импорт Excel</h2>
        <Field label="Тип файла"><Select disabled={busy} value={mode} onChange={(value) => { setMode(value); setSource(null); setMessage(''); }} options={[snapshotMode, clientMode]} /></Field>
        {mode === snapshotMode && <>
          <Field label="Отчётный период"><Select value={period} onChange={setPeriod} options={periods} disabled={busy} /></Field>
          <Field label="Дата среза"><input type="date" required value={date} onChange={(event) => setDate(event.target.value)} disabled={busy} /></Field>
        </>}
        <div className="field"><span>Excel-файл</span>
          <input ref={input} type="file" accept=".xlsx" hidden onChange={(event) => { choose(event.target.files[0]); event.target.value = ''; }} />
          <button type="button" className="dropzone" disabled={busy} onClick={() => input.current.click()} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); if (!busy) choose(event.dataTransfer.files[0]); }}>
            <strong>{source?.name || 'Перетащите .xlsx сюда или выберите файл'}</strong><small>До 10 МБ</small>
          </button>
        </div>
        <div className="between"><Button disabled={busy} onClick={() => input.current.click()}>Выбрать файл</Button><Button type="submit" primary disabled={!source || busy}>{busy ? 'Проверяем…' : 'Предпросмотр'}</Button></div>
      </form>
      <aside className="card stack">
        <h2>Требования к файлу</h2>
        <ul><li>{mode === clientMode ? 'Код КЦР, ИНН, Название организации' : 'Код КЦР, Документов всего, Не передано документов'}</li><li>При ошибке сервер отклоняет весь файл.</li></ul>
        {mode === snapshotMode && <><h3>Демо · примеры срезов</h3>
          <div className="row wrap">{sampleNames.map((name, index) => <Button disabled={busy} key={name} onClick={() => { setMessage(''); setSource({ name: 'Демо · ' + name, duplicate: index === 1 }); }}>{name}</Button>)}</div></>}
        <h3>Загрузки за эту сессию</h3>
        {batches.length ? batches.map((batch, index) => <div className="inset" key={index}><strong>{batch.name}</strong><div className="muted">{batch.date && dateText(batch.date) + ' · '}{batch.accepted} принято</div></div>) : <p>Загрузок пока нет.</p>}
      </aside>
    </div> : <section className="card stack">
      <div className="between">
        <div><h2>{done ? 'Импорт завершён' : fatal ? 'Файл отклонён' : showRows ? 'В файле есть ошибки' : 'Предварительный просмотр'}</h2><p>{meta.name}{meta.date && ' · ' + meta.period + ' · ' + dateText(meta.date)}</p></div>
        <Badge tone={done ? 'green' : fatal ? 'red' : report.errors.length ? 'amber' : 'blue'}>{done ? 'Завершено' : report.duplicates ? 'Дубликат' : report.errors.length ? 'Есть ошибки' : 'Предпросмотр'}</Badge>
      </div>
      <div className="metrics">
        {(!done || demo) && <Metric label={demo ? 'Строк в файле' : 'Строк на первом листе'} value={report.count} />}
        {done && <Metric label="Принято строк" value={result.created} />}
        {demo && !done && <Metric label="Готово к импорту" value={fatal ? 0 : report.accepted.length} />}
        {(demo || done) && <Metric label="Отклонено строк" value={fatal ? report.count : report.errors.length} />}
      </div>
      {fatal && <p className="notice red">{report.duplicates ? 'Удалите дубликаты идентификаторов и загрузите исправленный файл. Данные не сохранены.' : 'Исправьте ошибки и загрузите файл повторно.'}</p>}
      {!demo && !done && <p>Это предварительный просмотр первого листа. Сервер проверит файл перед сохранением.</p>}
      {done && <p>{source?.file
        ? 'Результат сохранён в базе.'
        : 'Демонстрационный пример: изменения только на экране, в базу не записаны.'}</p>}
      {(showRows || fatal) && !done && <Table headers={['Строка', 'Идентификатор', 'Причина']} label="Ошибки импорта">
        {report.errors.map(({ row, id, reason }) => <tr key={row}><td>{row}</td><td>{id || '—'}</td><td>{reason}</td></tr>)}
      </Table>}
      <div className="between">
        <div className="row wrap">
          {!done && <Button disabled={busy} onClick={() => { if (fatal) setSource(null); reset(); }}>{fatal ? 'Выбрать другой файл' : 'Назад к файлу'}</Button>}
          {report.errors.length > 0 && <Button onClick={() => downloadErrors(report.errors)}>Скачать отчёт ошибок</Button>}
        </div>
        {done ? <Button primary onClick={openClients}>Перейти к клиентам</Button> : !fatal && (report.errors.length && !showRows ?
          <Button primary onClick={() => setShowRows(true)}>Посмотреть ошибки</Button> :
          <Button disabled={busy} primary onClick={commit}>{busy ? 'Импортируем…' : demo ? 'Импортировать ' + report.accepted.length + ' строк' : 'Проверить и импортировать'}</Button>)}
      </div>
    </section>}
  </>;
}
