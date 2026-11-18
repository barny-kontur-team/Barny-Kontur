import { createRoot } from 'react-dom/client';
import { useEffect, useState } from 'react';
import '@fontsource-variable/inter';
import './styles.css';
import { Badge, Button, Field, Panel, Select } from './ui';
import { Assistant, ClientList, Queue, TodayScreen } from './ClientScreens';
import ClientCard from './ClientCard';
import ImportScreen from './ImportScreen';
import { applyImport, initialData, operators, saveCall, dateText, canCall, today } from './demo';

const accounts = {
  admin: { login: 'admin@example.test', phone: '+79000000001', name: 'Елена Соколова', label: 'Администратор' },
  operator: { login: 'operator@example.test', phone: '+79000000002', name: operators[0], label: 'Оператор' },
};
const password = 'demo1234';
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

function Login({ onLogin }) {
  const [login, setLogin] = useState('');
  const [secret, setSecret] = useState('');
  const [role, setRole] = useState('admin');
  const [error, setError] = useState('');
  const account = accounts[role];
  function submit(event) {
    event.preventDefault();
    const entered = login.trim().toLowerCase();
    const match = Object.entries(accounts).find(([, candidate]) => entered === candidate.login || entered.replace(/[\s()-]/g, '') === candidate.phone);
    if (!match || secret !== password) { setError('Неверная почта, телефон или пароль.'); return; }
    onLogin({ ...match[1], role: match[0] });
  }
  return <main className="login">
    <section className="login-cover">
      <div className="wordmark">КОНТУР</div>
      <h1>Контроль передачи<br />оригиналов документов</h1>
      <p>Единая история клиента, списки на обзвон и контроль повторных контактов.</p>
    </section>
    <section className="login-content">
      <form className="login-form" onSubmit={submit}>
        <h1>Вход в сервис</h1><p>Используйте рабочую почту или номер телефона.</p>
        <Field label="Почта или телефон"><input autoComplete="username" placeholder="Введите логин" value={login} onChange={(event) => { setLogin(event.target.value); setError(''); }} required /></Field>
        <Field label="Пароль" error={error}><input type="password" autoComplete="current-password" value={secret} onChange={(event) => { setSecret(event.target.value); setError(''); }} required /></Field>
        <Button type="submit" primary>Войти</Button>
        <div className="inset stack">
          <Field label="Демонстрационная роль"><Select options={Object.values(accounts).map((item) => item.label)} value={account.label} onChange={(label) => setRole(label === 'Оператор' ? 'operator' : 'admin')} /></Field>
          <p>{account.login} · пароль {password}</p>
          <Button onClick={() => { setLogin(account.login); setSecret(password); setError(''); }}>Подставить демоданные</Button>
        </div>
      </form>
    </section>
  </main>;
}

function App() {
  const [user, setUser] = useState(null);
  const [data, setData] = useState(initialData);
  const [page, setPage] = useState('clients');
  const [clientId, setClientId] = useState('');
  const [back, setBack] = useState('clients');
  const [notice, setNotice] = useState('');
  const [help, setHelp] = useState(false);
  useEffect(() => {
    if (!notice) return;
    const timeout = setTimeout(() => setNotice(''), 4500);
    return () => clearTimeout(timeout);
  }, [notice]);
  const nav = (next) => { setPage(next); window.scrollTo(0, 0); };
  if (!user) return <Login onLogin={(account) => { setUser(account); nav(account.role === 'admin' ? 'clients' : 'today'); }} />;

  const admin = user.role === 'admin';
  const pooled = data.clients.filter((client) => client.queued);
  const client = (admin ? data.clients : pooled).find((item) => item.id === clientId);
  const open = (id) => { setClientId(id); setBack(page); nav('client'); };
  const assign = (ids, owner, replace) => {
    if (!admin) return;
    setData((previous) => ({ ...previous, clients: previous.clients.map((item) => ids.includes(item.id) && (replace || !item.owner || item.owner === owner) ? { ...item, owner, queued: true } : item) }));
    setNotice(replace ? 'Ответственный изменён' : 'Клиенты назначены');
  };
  const take = (id) => {
    const candidate = pooled.find((item) => item.id === id);
    if (admin || !candidate || candidate.owner || !canCall(candidate)) return;
    setData((previous) => ({ ...previous, clients: previous.clients.map((item) => item.id === id && !item.owner ? { ...item, owner: user.name } : item) }));
    setNotice('Клиент взят в работу');
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
      <div className="profile"><strong>{user.name}</strong><span>{user.label} · демо</span><button className="text-button" type="button" onClick={() => { setNotice(''); setUser(null); }}>Выйти</button></div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div><h1>{title}</h1><p>{subtitle}</p></div>
        {page === 'assistant' ? <Badge>Только для чтения · демо</Badge> : <Button onClick={() => setHelp(true)}>Помощь</Button>}
      </header>
      <div className="content" key={page}>
        {page === 'clients' && admin && <ClientList clients={data.clients} open={open} onQueue={() => nav('queue')} />}
        {page === 'queue' && admin && <Queue clients={data.clients} open={open} assign={assign} />}
        {page === 'imports' && admin && <ImportScreen data={data} openClients={() => nav('clients')} onImport={(report, meta) => setData(applyImport(data, report, meta))} />}
        {page === 'today' && <TodayScreen clients={pooled} user={user} open={open} take={take} />}
        {page === 'assistant' && admin && <Assistant clients={data.clients} open={open} />}
        {page === 'client' && client && <div className="stack">
          <div><Button onClick={() => nav(back)}>Назад к списку</Button></div>
          <ClientCard key={client.id} client={client} user={user} take={() => take(client.id)} assign={(owner) => assign([client.id], owner, !!client.owner)}
            save={(form) => { setData((previous) => saveCall(previous, client.id, form, user.name)); setNotice('Звонок сохранён'); }}
            claim={(value) => {
              if (!admin) return;
              setData((previous) => ({ ...previous, clients: previous.clients.map((item) => item.id !== client.id ? item : {
                ...item, claims: [value, ...item.claims], tags: [...new Set([...item.tags, 'Претензия'])], stage: 'Претензия',
              }) }));
              setNotice('Претензия сохранена');
            }} />
        </div>}
      </div>
    </main>
    {notice && <div className="toast" role="status"><Badge tone="green">Готово</Badge><strong>{notice}</strong></div>}
    {help && <Panel title="Помощь" modal onClose={() => setHelp(false)}>
      <p>{admin ? 'Начните с загрузки Excel или откройте список клиентов, чтобы подготовить обзвон.' : 'Откройте «Сегодня нужно», выберите клиента и запишите результат контакта в карточке.'}</p>
      <p>Демонстрационные изменения сохраняются до перезагрузки страницы.</p>
      <div className="actions"><Button primary onClick={() => setHelp(false)}>Понятно</Button></div>
    </Panel>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
