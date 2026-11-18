import { useState } from 'react';
import { Badge, Button, Field, Metric, Panel, Select, Table } from './ui';
import { canCall, clientTags, dateStatus, dateText, dynamics, operators, priorities, recommendation, stages, today } from './demo';

function ClientLink({ client, open }) {
  return <button type="button" className="text-button" onClick={(event) => { event.stopPropagation(); open(client.id); }}>{client.name}</button>;
}

function matches(client, query, trend, tag) {
  const needle = query.trim().toLowerCase();
  return (!needle || [client.name.toLowerCase(), client.id, client.inn].some((value) => value.includes(needle)))
    && (!trend || trend === client.snapshots[0].trend) && (!tag || client.tags.includes(tag));
}

function Filters({ query, setQuery, trend, setTrend, tag, setTag }) {
  return <div className="row wrap">
    <input className="search" aria-label="Поиск клиентов" placeholder="Поиск по коду КЦР или ИНН" value={query} onChange={(event) => setQuery(event.target.value)} />
    <Select aria-label="Динамика" value={trend} onChange={setTrend} options={dynamics} empty="Динамика" />
    <Select aria-label="Метки" value={tag} onChange={setTag} options={clientTags} empty="Метки" />
  </div>;
}

function useFilters() {
  const [query, setQuery] = useState('');
  const [trend, setTrend] = useState('');
  const [tag, setTag] = useState('');
  return { query, setQuery, trend, setTrend, tag, setTag };
}

export function ClientList({ clients, open, onQueue }) {
  const filters = useFilters();
  const filtered = clients.filter((client) => matches(client, filters.query, filters.trend, filters.tag));
  const inWork = clients.filter((client) => client.owner && client.stage !== stages[5]).length;
  const latest = clients.reduce((date, client) => client.snapshots[0].date > date ? client.snapshots[0].date : date, '');
  return <div className="stack">
    <div className="metrics compact"><Metric label="Всего клиентов" value={clients.length} /><Metric label="В работе" value={inWork} /><Metric label="Нет данных" value={clients.filter((client) => !client.snapshots[0].total).length} /></div>
    <div className="between wrap"><Filters {...filters} /><div className="row"><span className="badge blue">Срез · {dateText(latest)}</span><Button primary onClick={onQueue}>Сформировать список</Button></div></div>
    <Table headers={['Код КЦР', 'Организация', 'Не передано / всего', 'Рабочий статус', 'Динамика и метки', 'Этап', 'Ответственный', 'Обещанный срок']} label="Клиенты" empty={!filtered.length}>
      {filtered.map((client) => <tr key={client.id} onClick={() => open(client.id)} className="clickable">
        <td>{client.id}</td><td><ClientLink client={client} open={open} /></td>
        <td>{client.snapshots[0].missing} / {client.snapshots[0].total}</td>
        <td>{client.stage === stages[5] ? <Badge>Работа завершена</Badge> : client.owner ? <Badge>В работе</Badge> : '—'}</td>
        <td><div className="row wrap badges"><Badge>{client.snapshots[0].trend}</Badge>{client.tags.map((tag) => <Badge key={tag}>{tag}</Badge>)}</div></td>
        <td>{client.stage}</td><td>{client.owner || '—'}</td>
        <td className="nowrap">{dateText(client.due)}{client.due && <div className={dateStatus(client.due) === 'Просрочен' ? 'error-text' : 'muted'}>{dateStatus(client.due)}</div>}</td>
      </tr>)}
    </Table>
  </div>;
}

export function TodayScreen({ clients, user, open, take }) {
  const filters = useFilters();
  const [tab, setTab] = useState('Сегодня');
  const [pending, setPending] = useState(null);
  const groups = {
    'Просрочено': clients.filter((client) => client.next && client.next < today),
    'Сегодня': clients.filter((client) => client.next === today || !client.next),
    'Неделя': clients.filter((client) => client.next > today && client.next <= '2026-10-31'),
  };
  const shown = groups[tab].filter((client) => matches(client, filters.query, filters.trend, filters.tag));
  return <div className="stack">
    <div className="metrics compact">{Object.entries(groups).map(([name, group]) => <Metric key={name} label={name} value={group.length} note={name === 'Сегодня' ? 'Задачи и клиенты без даты' : undefined} />)}</div>
    <div className="between wrap">
      <div className="tabs" aria-label="Период задач">{Object.keys(groups).map((name) => <Button key={name} aria-pressed={tab === name} primary={tab === name} onClick={() => setTab(name)}>{name} · {groups[name].length}</Button>)}</div>
      <Filters {...filters} />
    </div>
    <Table headers={['Срок', 'Клиент', 'Что сделать', 'Этап', 'Ответственный', 'Действие']} label="Сегодня нужно" empty={!shown.length}>
      {shown.map((client) => <tr key={client.id} onClick={() => open(client.id)} className="clickable">
        <td className="nowrap">{client.next ? dateText(client.next) : '—'}</td>
        <td><ClientLink client={client} open={open} /><div className="muted">{client.id}</div></td>
        <td>{recommendation(client)}</td><td>{client.stage}</td><td>{client.owner || 'Не назначен'}</td>
        <td>{client.owner === user.name ? <Badge tone="green">В работе у вас</Badge> : client.owner ? <span className="muted">В работе у коллеги</span> :
          <Button primary disabled={!canCall(client)} onClick={(event) => { event.stopPropagation(); setPending(client); }}>Взять в работу</Button>}</td>
      </tr>)}
    </Table>
    {pending && <Panel modal title="Взять в работу" subtitle={pending.name} onClose={() => setPending(null)}>
      <p>Клиент закрепится за вами после подтверждения.</p>
      <div className="actions"><Button onClick={() => setPending(null)}>Отмена</Button><Button primary onClick={() => { take(pending.id); setPending(null); }}>Подтвердить</Button></div>
    </Panel>}
  </div>;
}

export function Queue({ clients, open, assign }) {
  const defaults = { threshold: '5', trend: '', tag: '', stage: '', term: '' };
  const [draft, setDraft] = useState(defaults);
  const [filters, setFilters] = useState(defaults);
  const [checked, setChecked] = useState([]);
  const [panel, setPanel] = useState(false);
  const [owner, setOwner] = useState(operators[0]);
  const [confirm, setConfirm] = useState(false);
  const visible = clients.filter((client) => canCall(client, Number(filters.threshold || 0))
    && matches(client, '', filters.trend, filters.tag) && (!filters.stage || filters.stage === client.stage)
    && (!filters.term || filters.term === (dateStatus(client.due) || 'Срок не указан')));
  const selection = visible.filter((client) => checked.includes(client.id));
  const free = selection.filter((client) => !client.owner);
  const assigned = selection.filter((client) => client.owner && client.owner !== owner);
  const sameOwner = selection.filter((client) => client.owner === owner && !client.queued);
  const set = (key, value) => setDraft((previous) => ({ ...previous, [key]: value }));
  function apply(items, replace) {
    assign(items.map((client) => client.id), owner, replace);
    setChecked((list) => list.filter((id) => !items.some((client) => client.id === id)));
    setPanel(false);
    setConfirm(false);
  }
  return <div className="stack">
    <form className="card" onSubmit={(event) => { event.preventDefault(); setFilters(draft); setChecked([]); }}>
      <h2>Условия выборки</h2>
      <div className="filter-grid">
        <Field label="Доля непереданных, от %"><input type="number" min="0" max="100" value={draft.threshold} onChange={(event) => set('threshold', event.target.value)} /></Field>
        <Field label="Метки"><Select value={draft.tag} onChange={(value) => set('tag', value)} options={clientTags.slice(0, 2)} empty="Все" /></Field>
        <Field label="Этап"><Select value={draft.stage} onChange={(value) => set('stage', value)} options={stages} empty="Все этапы" /></Field>
        <Field label="Динамика"><Select value={draft.trend} onChange={(value) => set('trend', value)} options={dynamics} empty="Любая" /></Field>
        <Field label="Обещанный срок"><Select value={draft.term} onChange={(value) => set('term', value)} options={['Просрочен', 'Сегодня', 'Срок не указан']} empty="Любой" /></Field>
      </div>
      <div className="row"><Button type="submit" primary>Применить фильтры</Button><Button onClick={() => { setDraft(defaults); setFilters(defaults); setChecked([]); }}>Сбросить</Button></div>
    </form>
    <div className="between wrap"><h2>Найдено: {visible.length}</h2><div className="row"><span className="badge blue">Выбрано: {selection.length}</span><Button primary disabled={!selection.length} onClick={() => { setConfirm(false); setPanel(true); }}>Добавить в обзвон</Button></div></div>
    <Table headers={['Выбор', 'Код КЦР', 'Клиент', 'Доля', 'Динамика', 'Текущий этап', 'Ответственный']} label="Список на обзвон" empty={!visible.length}>
      {visible.map((client) => <tr key={client.id}>
        <td><input aria-label={'Выбрать ' + client.name} type="checkbox" checked={checked.includes(client.id)} onChange={(event) => setChecked((ids) => event.target.checked ? [...ids, client.id] : ids.filter((id) => id !== client.id))} /></td>
        <td>{client.id}</td><td><ClientLink client={client} open={open} /></td>
        <td>{(client.snapshots[0].missing / client.snapshots[0].total * 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%</td>
        <td><Badge>{client.snapshots[0].trend}</Badge></td><td>{client.stage}</td><td>{client.owner || '—'}</td>
      </tr>)}
    </Table>
    {panel && <Panel title={confirm ? 'Подтвердите переназначение' : 'Назначение операторов'} subtitle={'Выбрано клиентов: ' + selection.length} onClose={() => setPanel(false)}>
      {confirm ? <>
        <p>Новый ответственный — {owner}.</p><ul>{assigned.map((client) => <li key={client.id}>{client.name} · сейчас {client.owner}</li>)}</ul>
        <div className="actions"><Button onClick={() => setConfirm(false)}>Назад</Button><Button primary onClick={() => apply(assigned, true)}>Подтвердить</Button></div>
      </> : <>
        <div className="metrics"><Metric label="Без ответственного" value={free.length} /><Metric label="У другого оператора" value={assigned.length} /></div>
        <Field label="Ответственный оператор"><Select value={owner} onChange={setOwner} options={operators} /></Field>
        <div className="row wrap"><Button primary disabled={!free.length} onClick={() => apply(free, false)}>Назначить свободных · {free.length}</Button><Button disabled={!assigned.length} onClick={() => setConfirm(true)}>Переназначить · {assigned.length}</Button></div>
        {sameOwner.length > 0 && <div className="row"><Button onClick={() => apply(sameOwner, false)}>Добавить в пул · {sameOwner.length}</Button></div>}
        <p>Переназначение требует подтверждения. У клиента один ответственный.</p>
      </>}
    </Panel>}
  </div>;
}

export function Assistant({ clients, open }) {
  const [query, setQuery] = useState('');
  const [asked, setAsked] = useState('Составь приоритетный список на сегодня');
  const [expanded, setExpanded] = useState(false);
  const ranked = priorities(clients);
  const matching = clients.find((client) => asked.includes(client.id) || asked.includes(client.inn) || asked.toLowerCase().includes(client.name.toLowerCase().split('«')[1]?.split('-')[0]));
  const overdue = ranked.filter((client) => client.next && client.next < today);
  const asksForPriority = /приоритет|обзвон|первым/i.test(asked);
  function ask(value) { if (value.trim()) { setAsked(value.trim()); setQuery(''); } }
  const answer = matching ? recommendation(matching) : /просроч/i.test(asked) ? 'Клиентов с просроченным контактом в списке приоритетов: ' + overdue.length + '.' :
    asksForPriority ? 'Подходящих клиентов: ' + ranked.length + '. В начале списка — просроченные контакты, затем хронические случаи.' : 'Для ответа укажите код КЦР, ИНН или спросите о приоритетах и просроченных контактах.';
  return <div className="split">
    <section className="card stack">
      <h2>Задайте вопрос по клиентам</h2>
      <div className="row wrap">{['Кого обзвонить первым?', 'Сколько просрочено?', 'Сводка по 1000001'].map((item) => <Button key={item} onClick={() => ask(item)}>{item}</Button>)}</div>
      <div className="question">{asked}</div><div className="inset"><h3>{matching?.name || 'Ответ помощника'}</h3><p>{answer}</p>{matching && <ClientLink client={matching} open={open} />}</div>
      <form className="row" onSubmit={(event) => { event.preventDefault(); ask(query); }}><input className="grow" aria-label="Вопрос помощнику" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Спросите о клиентах, сроках или этапах" /><Button primary type="submit">Отправить</Button></form>
    </section>
    <aside className="stack">
      <section className="card stack"><h2>Приоритет на сегодня</h2>
        {ranked.slice(0, expanded ? ranked.length : 4).map((client) => <div className="inset" key={client.id}><ClientLink client={client} open={open} /><div className="muted">{client.next && client.next < today ? 'Просроченный контакт · ' : ''}{recommendation(client)}</div></div>)}
        {!ranked.length && <p>Подходящих клиентов нет.</p>}
        {ranked.length > 4 && <Button primary onClick={() => setExpanded(!expanded)}>{expanded ? 'Свернуть список' : 'Открыть список'}</Button>}
      </section>
      <section className="card"><h2>Что умеет помощник</h2><p>Даёт сводку по клиенту и подсказывает порядок обзвона. Только для чтения.</p></section>
    </aside>
  </div>;
}
