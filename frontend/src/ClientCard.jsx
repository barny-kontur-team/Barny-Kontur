import { useState } from 'react';
import { Badge, Button, Field, Metric, Panel, Select } from './ui';
import { canCall, dateStatus, dateText, recommendation, stages, today } from './demo';

function CallForm({ client, close, onSave }) {
  const [form, setForm] = useState({ result: 'Дозвонились', comment: '', agreement: '', due: '', next: '', stage: client.stage, backdated: false, date: '' });
  const [errors, setErrors] = useState({});
  const set = (key, value) => {
    setForm((previous) => ({ ...previous, [key]: value }));
    setErrors((previous) => ({ ...previous, [key]: undefined }));
  };
  function save(event) {
    event.preventDefault();
    const invalid = {};
    if (!form.due) invalid.due = 'Укажите обещанный срок.';
    if (form.backdated && (!form.date || form.date > today)) invalid.date = 'Укажите фактическую дату, не позднее сегодняшней.';
    if (Object.keys(invalid).length) { setErrors(invalid); return; }
    onSave(form);
  }
  return <Panel title="Записать звонок" subtitle={client.name + ' · КЦР ' + client.id} onClose={close}>
    <form className="stack" onSubmit={save} noValidate>
      <h3>Контакт</h3>
      <Field label="Результат контакта"><Select value={form.result} onChange={(value) => set('result', value)} options={['Дозвонились', 'Не дозвонились', 'Отказ']} /></Field>
      <Field label="Комментарий"><textarea rows="2" value={form.comment} onChange={(event) => set('comment', event.target.value)} /></Field>
      <Field label="Договорённость"><input value={form.agreement} onChange={(event) => set('agreement', event.target.value)} /></Field>
      <h3>Следующие шаги</h3>
      <div className="two-fields">
        <Field label="Обещанный срок *" error={errors.due}><input aria-invalid={!!errors.due} required type="date" value={form.due} onChange={(event) => set('due', event.target.value)} /></Field>
        <Field label="Следующий контакт"><input type="date" value={form.next} onChange={(event) => set('next', event.target.value)} /></Field>
      </div>
      <Field label="Следующий этап"><Select value={form.stage} onChange={(value) => set('stage', value)} options={stages} /></Field>
      <label className="switch"><input type="checkbox" checked={form.backdated} onChange={(event) => {
        set('backdated', event.target.checked);
        if (!event.target.checked) setErrors((previous) => ({ ...previous, date: undefined }));
      }} /><span>Звонок задним числом</span></label>
      {form.backdated && <Field label="Фактическая дата звонка *" error={errors.date}><input aria-invalid={!!errors.date} required type="date" max={today} value={form.date} onChange={(event) => set('date', event.target.value)} /></Field>}
      <div className="actions"><Button onClick={close}>Отмена</Button><Button primary type="submit" disabled={!!(errors.due || errors.date)}>Сохранить звонок</Button></div>
    </form>
  </Panel>;
}

function ClaimForm({ client, close, save }) {
  const [status, setStatus] = useState('Подготовлена');
  return <Panel title="Добавить претензию" subtitle={client.name} onClose={close}>
    <form className="stack" onSubmit={(event) => {
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      const number = values.get('number').trim();
      if (number) save({ number, date: values.get('date'), status, sanction: values.get('sanction').trim() });
    }}>
      <Field label="Номер претензии"><input name="number" required pattern=".*\S.*" /></Field>
      <Field label="Дата"><input name="date" type="date" defaultValue={today} required /></Field>
      <Field label="Статус"><Select value={status} onChange={setStatus} options={['Подготовлена', 'Направлена', 'Получена клиентом']} /></Field>
      <Field label="Санкции"><input name="sanction" placeholder="Если применены" /></Field>
      <div className="actions"><Button onClick={close}>Отмена</Button><Button primary type="submit">Сохранить претензию</Button></div>
    </form>
  </Panel>;
}

export default function ClientCard({ client, user, save, assign, take, claim, operators = [] }) {
  const [panel, setPanel] = useState('');
  const [owner, setOwner] = useState(client.owner || operators[0] || '');
  const close = () => setPanel('');
  const snapshot = client.snapshots[0];
  const last = client.calls[0];
  const admin = user.role === 'admin';
  const mayRecord = (admin || client.owner === user.name) && canCall(client, 0);
  const events = [...client.snapshots.map((item) => ({ ...item, kind: 'snapshot' })),
    ...client.calls.map((item) => ({ ...item, kind: 'call' }))]
    .sort((a, b) => b.date.localeCompare(a.date) || Number(b.kind === 'call') - Number(a.kind === 'call'));
  return <div className="stack">
    <div className="row wrap badges">{client.tags.map((tag) => <Badge key={tag}>{tag}</Badge>)}<Badge>{client.stage}</Badge>{client.owner && client.stage !== stages[5] && <Badge tone="amber">{'В работе: ' + client.owner}</Badge>}</div>
    <div className="metrics compact">
      <Metric label="Не передано" value={snapshot.missing + ' из ' + snapshot.total} note={snapshot.trend} />
      <Metric label="Прошлый срез" value={client.snapshots[1] ? client.snapshots[1].missing + ' из ' + client.snapshots[1].total : '—'} />
      <Metric label="Обещанный срок" value={dateText(client.due)} note={dateStatus(client.due)} />
      <Metric label="Следующий контакт" value={dateText(client.next)} note={dateStatus(client.next)} />
    </div>
    <div className="split card-split">
      <div className="stack">
        <section className="card"><h2>Текущая договорённость</h2><p>{last?.agreement || 'Договорённость пока не зафиксирована.'}</p>{last && <p>Последний контакт: {dateText(last.date)} · {last.author}</p>}</section>
        <section className="card"><h2>История клиента</h2>
          <ul className="timeline">{events.map((event) => <li key={event.id || 'snapshot-' + event.date}>
            <strong>{dateText(event.date)}{event.time && ' · ' + event.time} · {event.kind === 'call' ? 'Звонок' : 'Срез'}</strong>
            {event.kind === 'call' ? <><p>{event.result} · {event.author}</p>{event.agreement && <p>{event.agreement}</p>}{event.comment && <p>{event.comment}</p>}<p>Обещанный срок: {dateText(event.due)}</p></> :
              <p>{event.missing} из {event.total} не передано · {event.trend}</p>}
          </li>)}</ul>
        </section>
      </div>
      <aside className="stack">
        <section className="card"><h2>Сводка перед звонком</h2><p>{recommendation(client)}</p><Button onClick={() => setPanel('summary')}>Сводка ИИ</Button></section>
        <section className="card"><h2>Действия</h2><div className="row wrap">
          <Button primary disabled={!mayRecord} onClick={() => setPanel('call')}>Зафиксировать звонок</Button>
          {!admin && !client.owner && canCall(client) && <Button onClick={() => setPanel('take')}>Взять в работу</Button>}
          {admin && <><Button onClick={() => { setOwner(client.owner || operators[0] || ''); setPanel('owner'); }}>{client.owner ? 'Переназначить' : 'Назначить'}</Button><Button onClick={() => setPanel('claim')}>Добавить претензию</Button></>}
        </div>{!admin && client.owner && client.owner !== user.name && <p>Ответственный — {client.owner}. Переназначение доступно администратору.</p>}
          {!canCall(client, 0) && <p>{recommendation(client)}</p>}</section>
        <section className="card"><h2>Претензии и санкции</h2>{client.claims.length ? client.claims.map((item, index) => <div className="inset" key={index}><strong>{item.number} · {dateText(item.date)}</strong><p>{item.status}. {item.sanction || 'Санкции не применены.'}</p></div>) : <p>Активных претензий нет. Санкции не применены.</p>}</section>
        <section className="card recommendation"><h2>Рекомендуемое действие</h2><p>{recommendation(client)}</p></section>
      </aside>
    </div>
    {panel === 'call' && <CallForm client={client} close={close} onSave={(form) => { save(form); close(); }} />}
    {panel === 'claim' && admin && <ClaimForm client={client} close={close} save={(value) => { claim(value); close(); }} />}
    {panel === 'summary' && <Panel title="Сводка ИИ" subtitle={client.name} onClose={close}>
      <div className="stack"><Badge>Только для чтения · демо</Badge><div className="inset"><h3>Кратко о клиенте</h3><p>{snapshot.missing} из {snapshot.total} документов не передано.</p><p>{last ? 'Последний звонок: ' + dateText(last.date) + '. ' + (last.agreement || '') : 'Звонки пока не зафиксированы.'}</p><p>Обещанный срок: {dateText(client.due)}</p></div>
        <div className="card"><h3>Следующее действие</h3><p>{recommendation(client)}</p></div></div>
    </Panel>}
    {panel === 'owner' && admin && <Panel title={client.owner ? 'Переназначить клиента' : 'Назначить оператора'} subtitle={client.name} onClose={close}>
      {client.owner && <p>Текущий ответственный — {client.owner}.</p>}
      <Field label="Новый ответственный"><Select value={owner} onChange={setOwner} options={operators} /></Field>
      <div className="actions"><Button onClick={close}>Отмена</Button><Button primary disabled={owner === client.owner} onClick={() => { assign(owner); close(); }}>Подтвердить</Button></div>
    </Panel>}
    {panel === 'take' && <Panel modal title="Взять в работу" subtitle={client.name} onClose={close}><p>Клиент закрепится за вами после подтверждения.</p><div className="actions"><Button onClick={close}>Отмена</Button><Button primary onClick={() => { take(); close(); }}>Подтвердить</Button></div></Panel>}
  </div>;
}
