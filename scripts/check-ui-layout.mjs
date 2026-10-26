// Isolated layout regression: serves dist and synthetic API responses on a random
// loopback port. Never connects to the owner's API, database or browser profile.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';

const root = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../apps/web/dist',
);
await readFile(join(root, 'index.html')); // Require an explicit build first.
const tag = {
  id: 'layout-tag',
  name: '长标签名称'.repeat(8),
  created_at: '2026-10-26T00:00:00Z',
};
const entry = {
  id: 'layout-entry',
  entry_date: '2026-10-26',
  content_md: '# 合成布局记录\n\n' + 'LongWordWithoutSpaces'.repeat(30),
  created_at: tag.created_at,
  updated_at: tag.created_at,
  revision: 1,
  is_pinned: false,
  tags: [tag],
  assets: [],
};
const session = {
  user: {
    id: 'layout-owner',
    username: 'layout-owner',
    timezone: 'Asia/Shanghai',
  },
  csrf_token: 'synthetic-layout-token',
};
let signedIn = false;
const unexpected = [];
const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/api/')) {
    response.setHeader('Content-Type', 'application/json');
    response.setHeader('Cache-Control', 'no-store');
    const send = (body, status = 200) => {
      response.statusCode = status;
      response.end(JSON.stringify(body));
    };
    if (url.pathname === '/api/v1/health') return send({ status: 'ok' });
    if (url.pathname === '/api/v1/auth/login') {
      signedIn = true;
      return send(session);
    }
    if (url.pathname === '/api/v1/auth/me')
      return send(signedIn ? session : {}, signedIn ? 200 : 401);
    if (!signedIn) return send({}, 401);
    if (request.method !== 'GET') {
      unexpected.push(`${request.method} ${url.pathname}`);
      return send({}, 405);
    }
    if (url.pathname === '/api/v1/tags')
      return send({ items: [tag], next_cursor: null });
    if (url.pathname === '/api/v1/entries')
      return send({ items: [entry], next_cursor: null });
    if (url.pathname === '/api/v1/trash')
      return send({ items: [], next_cursor: null });
    if (url.pathname === '/api/v1/calendar')
      return send({
        year: Number(url.searchParams.get('year')),
        month: Number(url.searchParams.get('month')),
        days: [],
      });
    if (url.pathname.startsWith('/api/v1/days/'))
      return send({
        date: url.pathname.split('/').at(-1),
        entries: { items: [], next_cursor: null },
      });
    unexpected.push(`${request.method} ${url.pathname}`);
    return send({}, 404);
  }
  try {
    const path = resolve(
      root,
      `.${decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname)}`,
    );
    if (!path.startsWith(root + sep))
      throw new Error('Outside build directory');
    response.setHeader(
      'Content-Type',
      { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }[
        extname(path)
      ] ?? 'application/octet-stream',
    );
    response.end(await readFile(path));
  } catch {
    response.statusCode = 404;
    response.end();
  }
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
const profile = await mkdtemp(join(tmpdir(), 'lifearchive-ui-'));
const executable =
  process.env.CHROME_BIN ??
  (process.platform === 'darwin'
    ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    : 'google-chrome');
const chrome = spawn(
  executable,
  [
    '--headless=new',
    '--disable-background-networking',
    '--disable-extensions',
    '--no-first-run',
    '--remote-debugging-port=0',
    `--user-data-dir=${profile}`,
    ...(process.env.CI === 'true' ? ['--no-sandbox'] : []),
    'about:blank',
  ],
  { stdio: ['ignore', 'ignore', 'pipe'] },
);
let log = '';
chrome.stderr.on('data', (chunk) => {
  log = (log + chunk).slice(-4000);
});
chrome.on('error', (error) => {
  log = error.message;
});
let socket;
try {
  let port;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (chrome.exitCode !== null) throw new Error(`Chrome exited: ${log}`);
    try {
      port = (
        await readFile(join(profile, 'DevToolsActivePort'), 'utf8')
      ).split('\n')[0];
    } catch {
      /* Still starting. */
    }
    if (port) break;
    await delay(100);
  }
  assert.ok(port, `Chrome did not start: ${log}`);
  const browser = await (
    await fetch(`http://127.0.0.1:${port}/json/version`)
  ).json();
  socket = new WebSocket(browser.webSocketDebuggerUrl);
  await new Promise((done, reject) => {
    socket.addEventListener('open', done, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  let nextId = 0;
  const pending = new Map();
  socket.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data);
    const item = pending.get(message.id);
    if (!item) return;
    clearTimeout(item.timer);
    pending.delete(message.id);
    if (message.error) item.reject(new Error(message.error.message));
    else item.done(message.result);
  });
  function send(method, params = {}, sessionId) {
    return new Promise((done, reject) => {
      const id = ++nextId;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`Timed out: ${method}`));
      }, 10000);
      pending.set(id, { done, reject, timer });
      socket.send(JSON.stringify({ id, method, params, sessionId }));
    });
  }
  const { targetId } = await send('Target.createTarget', {
    url: 'about:blank',
  });
  const { sessionId } = await send('Target.attachToTarget', {
    targetId,
    flatten: true,
  });
  const cdp = (method, params = {}) => send(method, params, sessionId);
  async function evaluate(expression) {
    const result = await cdp('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    assert.ok(
      !result.exceptionDetails,
      JSON.stringify(result.exceptionDetails),
    );
    return result.result.value;
  }
  async function wait(expression) {
    for (let attempt = 0; attempt < 100; attempt++) {
      if (await evaluate(expression)) return;
      await delay(50);
    }
    throw new Error(`Condition timed out: ${expression}`);
  }
  async function click(label) {
    await evaluate(
      `(() => { const b = [...document.querySelectorAll('button')].find(b => b.getClientRects().length && b.textContent.trim() === ${JSON.stringify(label)}); if (!b || b.disabled) throw Error('Unavailable button: ' + ${JSON.stringify(label)}); b.click(); })()`,
    );
    await evaluate(
      'new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)))',
    );
  }
  async function viewport(width) {
    await cdp('Emulation.setDeviceMetricsOverride', {
      width,
      height: 1000,
      deviceScaleFactor: 1,
      mobile: width < 768,
    });
    await evaluate('new Promise(done => requestAnimationFrame(done))');
  }
  async function checkLayout(name) {
    const result = await evaluate(`(() => {
      const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
      const clipped = [...document.querySelectorAll('main *, .sidebar *')].filter(el => {
        if (!visible(el) || el.closest('.workspace-navigation')) return false;
        const r = el.getBoundingClientRect();
        return r.width && (r.left < -1 || r.right > innerWidth + 1);
      }).map(el => el.tagName + '.' + el.className);
      const small = [...document.querySelectorAll('button, a.primary-button, a.secondary-button')].filter(el => {
        if (!visible(el)) return false;
        const r = el.getBoundingClientRect();
        return r.width < 43.9 || r.height < 43.9;
      }).map(el => el.textContent.trim());
      return { width: innerWidth, scroll: document.documentElement.scrollWidth, clipped, small };
    })()`);
    assert.ok(
      result.scroll <= result.width,
      `${name}: horizontal overflow ${JSON.stringify(result)}`,
    );
    assert.deepEqual(result.clipped, [], `${name}: content clipped`);
    assert.deepEqual(result.small, [], `${name}: small touch targets`);
  }
  await cdp('Page.enable');
  await cdp('Page.navigate', { url: baseUrl });
  await wait('Boolean(document.querySelector("#username"))');
  for (const width of [320, 375, 414, 768, 1440]) {
    await viewport(width);
    await checkLayout(`login ${width}`);
  }
  await evaluate(
    `(() => { for (const [id, value] of [['username', 'layout-owner'], ['password', 'synthetic-password']]) { const input = document.getElementById(id); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); } })()`,
  );
  await click('登录');
  await wait('Boolean(document.querySelector("#journal-content"))');
  await wait('Boolean(document.querySelector(".entry-card"))');
  await evaluate(
    `(() => { const input = document.querySelector('#journal-content'); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, '尚未保存的布局草稿'); input.dispatchEvent(new Event('input', { bubbles: true })); window.layoutEditor = input; })()`,
  );
  for (const width of [320, 375, 414, 768, 1440]) {
    await viewport(width);
    for (const label of [
      '日记',
      '日历',
      '归档',
      '回收站',
      '标签管理',
      '导出',
      '账户',
    ]) {
      await click(label);
      if (label === '日历')
        await wait('Boolean(document.querySelector(".calendar-grid"))');
      if (label === '标签管理')
        await wait('Boolean(document.querySelector(".tag-catalogue"))');
      await checkLayout(`${label} ${width}`);
    }
    await click('日记');
    assert.ok(
      await evaluate(
        'document.querySelector("#journal-content") === window.layoutEditor && window.layoutEditor.value === "尚未保存的布局草稿"',
      ),
      'Navigation lost the editor',
    );
    await click('标签与图片');
    await checkLayout(`journal tools ${width}`);
    await click('标签与图片');
    console.log(
      `PASS: ${width}px — login, seven views, tools, touch targets and preserved draft`,
    );
  }
  await cdp('Emulation.setEmulatedMedia', {
    features: [
      { name: 'prefers-reduced-motion', value: 'reduce' },
      { name: 'prefers-contrast', value: 'more' },
    ],
  });
  assert.equal(
    await evaluate(
      'getComputedStyle(document.querySelector(".primary-button")).transitionDuration',
    ),
    '1e-05s',
  );
  assert.equal(
    await evaluate(
      'getComputedStyle(document.documentElement).getPropertyValue("--line").trim()',
    ),
    '#888892',
  );
  assert.deepEqual(
    unexpected,
    [],
    'Unexpected API request in isolated fixture',
  );
  console.log('PASS: reduced motion and increased contrast');
} finally {
  socket?.close();
  chrome.kill('SIGTERM');
  await new Promise((done) => server.close(done));
}
