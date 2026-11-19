import { createRoot } from 'react-dom/client';
import { useCallback, useEffect, useState } from 'react';
import '@fontsource-variable/inter';
import './styles.css';
import { Badge, Button, Field, Panel, Select } from './ui';
import { Assistant, ClientList, Queue, TodayScreen } from './ClientScreens';
import ClientCard from './ClientCard';
import ImportScreen from './ImportScreen';
import { api } from './api';
import { applyImport, dateText, stages, today } from './demo';

const password = 'demo1234';
const roleLabel = { ADMIN: 'Администратор', OPERATOR: 'Оператор' };
const menus = [
  ['clients', 'Клиенты'],
  ['today', 'Сегодня нужно'],
  ['queue', 'Список на обзвон'],
  ['imports', 'Загрузки'],
  ['assistant', 'ИИ-помощник'],
];
const subtitles = {
  clients: 'Текущий срез, этапы работы и ответственные',
  queue: 'Подберите клиентов и распределите список между операторами',
  imports: 'Проверка Excel и история загрузок',
  assistant: 'Сводки и приоритеты по данным сервиса',
};

function toApiPeriod(value) {
  return value.replace('квартал', 'кв.');
}

function toCall(call) {
  return {
    id: String(call.id),
    date: (call.created_at || '').slice(0, 10),
    time: (call.created_at || '').slice(11, 16),
    author: call.operator_name,
    result: call.result || '',
    agreement: call.comment || '',
    due: call.promised_date || '',
    recordedAt: call.created_at,
  };
}

function toClient(item, work, previous) {
  const history = (item.history || []).map((snapshot) => ({
    date: snapshot.date,
    missing: snapshot.missing,
    total: snapshot.total ?? 0,
    trend: snapshot.category,
  }));
  const snapshots = history.length
    ? [...history].reverse()
    : [{ date: '', missing: 0, total: 0, trend: 'Нет данных' }];
  const last = item.last;
  const tags = [];
  if (last?.is_chronic) tags.push('Хронический');
  if (last?.is_novice && last.missing > 0) tags.push('Новичок');
  if (item.do_not_call) tags.push('Не работать');
  if ((work?.stage || '') === 'Претензия') tags.push('Претензия');
  const lastCall = work?.last_call;
  return {
    dbId: item.id,
    id: item.kcr_code,
    inn: item.inn || '',
    name: item.name,
    owner: work?.operator_name || '',
    ownerId: work?.operator_id || null,
    stage: work?.stage || stages[0],
    tags,
    due: lastCall?.promised_date || '',
    next: lastCall?.promised_date || '',
    queued: Boolean(last?.in_pool),
    snapshots,
    calls: previous?.calls || [],
    claims: previous?.claims || [],
  };
}

function Login({ onLogin, users, bootError }) {
  const [login, setLogin] = useState('');
  const [secret, setSecret] = useState('');
  const [role, setRole] = useState('admin');
  const [error, setError] = useState('');
  const admin = users.find((user) => user.role === 'ADMIN') || users[0];
  const operator = users.find((user) => user.role === 'OPERATOR');
  const account = role === 'admin' ? admin : operator;

  function submit(event) {
    event.preventDefault();
    const entered = login.trim().toLowerCase();
    const match = users.find((user) => user.login.toLowerCase() === entered);
    if (!match || secret !== password) {
      setError('Неверная почта или пароль.');
      return;
    }
    onLogin({
      id: match.id,
      name: match.full_name,
      role: match.role.toLowerCase(),
      label: roleLabel[match.role] || match.role,
    });
  }

  return <main className="login">
    <section className="login-cover">
      <div className="wordmark">КОНТУР</div>
      <h1>Контроль передачи<br />оригиналов документов</h1>
      <p>Единая история клиента, списки на обзвон и контроль повторных контактов.</p>
    </section>
    <section className="login-content">
      <form className="login-form" onSubmit={submit}>
        <h1>Вход в сервис</h1><p>Используйте рабочую почту.</p>
        {bootError && <p className="notice red" role="alert">Сервис недоступен: {bootError}</p>}
        <Field label="Почта"><input autoComplete="username" placeholder="Введите логин" value={login} onChange={(event) => { setLogin(event.target.value); setError(''); }} required /></Field>
        <Field label="Пароль" error={error}><input type="password" autoComplete="current-password" value={secret} onChange={(event) => { setSecret(event.target.value); setError(''); }} required /></Field>
        <Button type="submit" primary disabled={!users.length}>Войти</Button>
        <div className="inset stack">
          <Field label="Демонстрационная роль"><Select options={['Администратор', 'Оператор']} value={role === 'admin' ? 'Администратор' : 'Оператор'} onChange={(label) => setRole(label === 'Оператор' ? 'operator' : 'admin')} /></Field>
          <p>{account ? account.login : 'пользователи не загружены'} · пароль {password}</p>
          <Button disabled={!account} onClick={() => { if (account) { setLogin(account.login); setSecret(password); setError(''); } }}>Подставить демоданные</Button>
        </div>
      </form>
    </section>
  </main>;
}

function App() {
  const [user, setUser] = useState(null);
  const [users, setUsers] = useState([]);
  const [bootError, setBootError] = useState('');
  const [data, setData] = useState({ clients: [], batches: [] });
  const [loading, setLoading] = useState(false);
  const [dataError, setDataError] = useState('');
  const [page, setPage] = useState('clients');
  const [clientId, setClientId] = useState('');
  const [back, setBack] = useState('clients');
  const [notice, setNotice] = useState('');
  const [help, setHelp] = useState(false);

  useEffect(() => {
    api.users().then((response) => setUsers(response.users)).catch((error) => setBootError(error.message));
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [clientsResponse, workResponse] = await Promise.all([api.clients(), api.work()]);
      const work = new Map(workResponse.work.map((item) => [item.client_id, item]));
      setData((previous) => ({
        batches: previous.batches,
        clients: clientsResponse.clients.map((item) => toClient(
          item,
          work.get(item.id),
          previous.clients.find((client) => client.dbId === item.id),
        )),
      }));
      setDataError('');
    } catch (error) {
      setDataError(error.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (user) refresh(); }, [user, refresh]);

  useEffect(() => {
    if (!notice) return;
    const timeout = setTimeout(() => setNotice(''), 4500);
    return () => clearTimeout(timeout);
  }, [notice]);

  const nav = (next) => { setPage(next); window.scrollTo(0, 0); };

  const loadCallsFor = async (dbId, kcrCode) => {
    if (!dbId) return;
    try {
      const response = await api.calls(dbId);
      setData((previous) => ({
        ...previous,
        clients: previous.clients.map((client) => client.id === kcrCode
          ? { ...client, calls: response.calls.map(toCall) }
          : client),
      }));
    } catch (error) {
      setNotice(error.message);
    }
  };

  if (!user) {
    return <Login
      users={users}
      bootError={bootError}
      onLogin={(account) => { setUser(account); nav(account.role === 'admin' ? 'clients' : 'today'); }}
    />;
  }

  const admin = user.role === 'admin';
  const operatorNames = users.filter((item) => item.role === 'OPERATOR').map((item) => item.full_name);
  const pooled = data.clients.filter((client) => client.queued);
  const client = (admin ? data.clients : pooled).find((item) => item.id === clientId);

  const open = (id) => {
    const target = data.clients.find((item) => item.id === id);
    setClientId(id);
    setBack(page);
    nav('client');
    if (target) loadCallsFor(target.dbId, id);
  };

  const take = async (id) => {
    const target = data.clients.find((item) => item.id === id);
    if (!target) return;
    try {
      await api.take(target.dbId, user.id);
      await refresh();
      setNotice('Клиент взят в работу');
    } catch (error) {
      setNotice(error.message);
    }
  };

  const assign = async (ids, ownerName, replace) => {
    if (!admin) return;
    const operator = users.find((item) => item.full_name === ownerName && item.role === 'OPERATOR');
    if (!operator) { setNotice('Оператор не найден'); return; }
    try {
      for (const id of ids) {
        const target = data.clients.find((item) => item.id === id);
        if (!target) continue;
        const takeover = Boolean(target.owner) && target.owner !== ownerName;
        if (takeover && !replace) continue;
        await api.take(target.dbId, operator.id, takeover);
      }
      await refresh();
      setNotice(replace ? 'Ответственный изменён' : 'Клиенты назначены');
    } catch (error) {
      setNotice(error.message);
    }
  };

  const saveCall = async (form) => {
    if (!client) return;
    try {
      // Если клиента ещё никто не взял, звонок автоматически закрепляет его за автором.
      if (!client.owner) await api.take(client.dbId, user.id);
      await api.addCall(client.dbId, {
        operator_id: user.id,
        promised_date: form.due,
        result: form.result || null,
        comment: [form.agreement, form.comment].filter(Boolean).join(' · ') || null,
        called_at: form.backdated && form.date ? `${form.date}T12:00:00` : null,
        stage: form.stage || null,
      });
      await refresh();
      await loadCallsFor(client.dbId, client.id);
      setNotice('Звонок сохранён');
    } catch (error) {
      setNotice(error.message);
    }
  };

  const handleImport = async (report, meta, file) => {
    if (!file) {
      setData((previous) => applyImport(previous, report, meta));
      return;
    }
    await api.importSnapshot(file, meta.date, toApiPeriod(meta.period));
    await refresh();
  };

  const title = page === 'client' ? client?.name || 'Карточка клиента' : menus.find(([id]) => id === page)?.[1];
  const subtitle = page === 'client' && client ? 'Код КЦР ' + client.id + ' · ИНН ' + client.inn :
    page === 'today' ? dateText(today) + ' · задачи на обзвон и проверку' : subtitles[page];

  return <div className="app">
    <aside className="sidebar">
      <div className="brand"><div className="wordmark">КОНТУР</div><strong>Контроль документов</strong></div>
      <nav aria-label="Основная навигация">
        {(admin ? menus : menus.filter(([id]) => id === 'today')).map(([id, label]) => <button key={id} type="button"
          className={page === id || (page === 'client' && back === id) ? 'active' : ''} aria-current={page === id ? 'page' : undefined} onClick={() => nav(id)}>{label}</button>)}
      </nav>
      <div className="profile"><strong>{user.name}</strong><span>{user.label}</span><button className="text-button" type="button" onClick={() => { setNotice(''); setUser(null); }}>Выйти</button></div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div><h1>{title}</h1><p>{subtitle}</p></div>
        {page === 'assistant' ? <Badge>Только для чтения · демо</Badge> : <Button onClick={() => setHelp(true)}>Помощь</Button>}
      </header>
      {dataError && <p className="notice red" role="alert">Не удалось загрузить данные: {dataError}</p>}
      {loading && <p className="muted">Обновляем данные…</p>}
      <div className="content" key={page}>
        {page === 'clients' && admin && <ClientList clients={data.clients} open={open} onQueue={() => nav('queue')} />}
        {page === 'queue' && admin && <Queue clients={data.clients} open={open} assign={assign} operators={operatorNames} />}
        {page === 'imports' && admin && <ImportScreen data={data} openClients={() => nav('clients')} onImport={handleImport} />}
        {page === 'today' && <TodayScreen clients={pooled} user={user} open={open} take={take} />}
        {page === 'assistant' && admin && <Assistant clients={data.clients} open={open} />}
        {page === 'client' && client && <div className="stack">
          <div><Button onClick={() => nav(back)}>Назад к списку</Button></div>
          <ClientCard key={client.id} client={client} user={user} operators={operatorNames}
            take={() => take(client.id)} assign={(owner) => assign([client.id], owner, Boolean(client.owner))}
            save={saveCall}
            claim={(value) => {
              if (!admin) return;
              setData((previous) => ({ ...previous, clients: previous.clients.map((item) => item.id !== client.id ? item : {
                ...item, claims: [value, ...item.claims], tags: [...new Set([...item.tags, 'Претензия'])], stage: 'Претензия',
              }) }));
              setNotice('Претензия сохранена (демо)');
            }} />
        </div>}
      </div>
    </main>
    {notice && <div className="toast" role="status"><Badge tone="green">Готово</Badge><strong>{notice}</strong></div>}
    {help && <Panel title="Помощь" modal onClose={() => setHelp(false)}>
      <p>{admin ? 'Начните с загрузки Excel или откройте список клиентов, чтобы подготовить обзвон.' : 'Откройте «Сегодня нужно», выберите клиента и запишите результат контакта в карточке.'}</p>
      <p>Клиенты, срезы и звонки сохраняются в базе. ИИ-помощник и претензии пока демонстрационные.</p>
      <div className="actions"><Button primary onClick={() => setHelp(false)}>Понятно</Button></div>
    </Panel>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
