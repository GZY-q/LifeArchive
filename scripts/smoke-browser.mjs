// Real Chrome/React/API smoke flow; only for an isolated loopback test deployment.
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const baseUrl = process.argv[2] ?? 'http://127.0.0.1:18080';
const project = process.env.COMPOSE_PROJECT_NAME ?? '';
const password = process.env.LIFEARCHIVE_SMOKE_PASSWORD;
const username = process.env.LIFEARCHIVE_SMOKE_USERNAME ?? 'm1-smoke-owner';
if (
  !/^life-archive-(ci-|smoke)/u.test(project) ||
  !password ||
  !['127.0.0.1', 'localhost'].includes(new URL(baseUrl).hostname)
) {
  throw new Error(
    'Browser smoke requires an isolated project, loopback URL and test owner password',
  );
}
const directory = await mkdtemp(join(tmpdir(), 'life-archive-browser-'));
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
    '--disable-component-update',
    '--disable-extensions',
    '--no-first-run',
    '--no-default-browser-check',
    '--remote-debugging-port=0',
    `--user-data-dir=${directory}`,
    ...(process.env.CI === 'true' ? ['--no-sandbox'] : []),
    'about:blank',
  ],
  { stdio: ['ignore', 'ignore', 'pipe'] },
);
let startupError = '';
let startupLog = '';
chrome.on('error', (error) => {
  startupError = error.message;
});
chrome.stderr.setEncoding('utf8');
chrome.stderr.on('data', (chunk) => {
  startupLog = (startupLog + chunk).slice(-8000);
});
let socket;
try {
  let port;
  for (let attempt = 0; attempt < 300; attempt += 1) {
    if (startupError || chrome.exitCode !== null || chrome.signalCode !== null)
      throw new Error(
        `Chrome startup failed (${startupError || (chrome.exitCode ?? chrome.signalCode)}): ${startupLog}`,
      );
    try {
      const candidate = (
        await readFile(join(directory, 'DevToolsActivePort'), 'utf8')
      ).split('\n')[0];
      if (/^\d+$/u.test(candidate)) {
        port = candidate;
        break;
      }
    } catch {
      // Chrome may still be starting or writing its endpoint file.
    }
    await delay(100);
  }
  if (!port)
    throw new Error(
      `Chrome did not provide a debugging endpoint: ${startupLog}`,
    );
  const browser = await (
    await fetch(`http://127.0.0.1:${port}/json/version`)
  ).json();
  socket = new WebSocket(browser.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  let nextId = 0;
  let allowDialog = false;
  let unexpectedDialog = false;
  let searchRequests = 0;
  let onThisDayRequests = 0;
  let unsafeSearchTransport = false;
  const pending = new Map();
  function send(method, params = {}, sessionId) {
    return new Promise((resolve, reject) => {
      const id = ++nextId;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`CDP timeout: ${method}`));
      }, 15000);
      pending.set(id, { resolve, reject, timer });
      socket.send(JSON.stringify({ id, method, params, sessionId }));
    });
  }
  socket.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data);
    if (message.method === 'Network.requestWillBeSent') {
      const request = message.params.request;
      const url = new URL(request.url);
      if (url.pathname === '/api/v1/on-this-day') onThisDayRequests += 1;
      if (url.pathname === '/api/v1/search') {
        searchRequests += 1;
        if (request.method !== 'POST' || url.search)
          unsafeSearchTransport = true;
      }
    }
    const item = pending.get(message.id);
    if (item) {
      clearTimeout(item.timer);
      pending.delete(message.id);
      if (message.error) item.reject(new Error(message.error.message));
      else item.resolve(message.result);
    }
    if (message.method === 'Page.javascriptDialogOpening') {
      if (!allowDialog) unexpectedDialog = true;
      void send(
        'Page.handleJavaScriptDialog',
        { accept: allowDialog },
        message.sessionId,
      );
    }
  });
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
    if (result.exceptionDetails)
      throw new Error(
        `Browser evaluation failed: ${result.exceptionDetails.text}`,
      );
    return result.result.value;
  }
  async function wait(expression) {
    for (let attempt = 0; attempt < 100; attempt += 1) {
      if (await evaluate(expression)) return;
      await delay(100);
    }
    throw new Error(`Browser condition timed out: ${expression}`);
  }
  async function click(label) {
    await evaluate(
      `(() => { const button = [...document.querySelectorAll('button')].find(item => item.getClientRects().length > 0 && item.textContent.trim() === ${JSON.stringify(label)}); if (!button || button.disabled) throw Error('Button unavailable'); button.click(); })()`,
    );
  }
  async function type(selector, text) {
    await evaluate(
      `(() => { const input = document.querySelector(${JSON.stringify(selector)}); input.focus(); input.select(); })()`,
    );
    await cdp('Input.insertText', { text });
  }
  async function selectCalendarDate(date) {
    await evaluate(
      `(() => { const input = document.querySelector('#calendar-date'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(date)}); input.dispatchEvent(new Event('input', { bubbles: true })); })()`,
    );
    await wait(
      `Boolean(document.querySelector('section[aria-label="${date} 的日记"]'))`,
    );
  }
  async function setDateInput(selector, value) {
    await evaluate(
      `(() => { const input = document.querySelector(${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(value)}); input.dispatchEvent(new Event('input', { bubbles: true })); })()`,
    );
  }
  async function searchArchive() {
    await wait(
      'document.querySelector("#archive-query")?.getClientRects().length > 0',
    );
    await wait(
      '[...document.querySelectorAll("button")].some(item => item.textContent.trim() === "搜索日记" && !item.disabled)',
    );
    await type('#archive-query', '中文输入');
    await setDateInput('#archive-date-from', '2001-02-03');
    await setDateInput('#archive-date-to', '2001-02-03');
    await click('搜索日记');
  }
  const api = (expression) => evaluate(`(async () => { ${expression} })()`);
  await cdp('Page.enable');
  await cdp('Network.enable');
  await cdp('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await cdp('Page.navigate', { url: baseUrl });
  await wait('Boolean(document.querySelector("#username"))');
  if (await evaluate('Boolean(document.querySelector("textarea"))'))
    throw new Error('Anonymous journal visible');
  await type('#username', username);
  await type('#password', password);
  await click('登录');
  await wait('Boolean(document.querySelector("#journal-content"))');
  const initial = await api(
    'return (await (await fetch("/api/v1/entries")).json()).items.length;',
  );
  if (initial !== 0)
    throw new Error('Browser smoke requires an empty active test journal');
  await evaluate('document.querySelector("#journal-content").focus()');
  await cdp('Input.imeSetComposition', {
    text: '中文输入',
    selectionStart: 4,
    selectionEnd: 4,
  });
  await wait(
    '[...document.querySelectorAll("button")].some(item => item.textContent.trim() === "保存日记" && item.disabled)',
  );
  await cdp('Input.insertText', { text: '中文输入' });
  await wait('document.querySelector("#journal-content").value === "中文输入"');
  const original =
    '# 浏览器验收\n\n中文输入与 Markdown。  \n<script>window.__unsafe=true</script>\n';
  await type('#journal-content', original);
  await evaluate(
    '(() => { const input = document.querySelector("#entry-date"); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, "2001-02-03"); input.dispatchEvent(new Event("input", { bubbles: true })); })()',
  );
  await click('日历');
  await wait('Boolean(document.querySelector("#calendar-date"))');
  await selectCalendarDate('2001-02-03');
  if (onThisDayRequests !== 0)
    throw new Error('Past-year journals loaded before explicit expansion');
  await click('展开往年这一天');
  await wait('document.body.textContent.includes("往年这一天还没有日记")');
  await click('日记');
  await wait(
    'document.querySelector("#journal-content").getClientRects().length > 0',
  );
  if (
    (await evaluate('document.querySelector("#journal-content").value')) !==
      original ||
    (await evaluate('document.querySelector("#entry-date").value')) !==
      '2001-02-03'
  )
    throw new Error('Calendar navigation lost unsaved Markdown or date');
  await click('归档');
  await wait('Boolean(document.querySelector("#archive-query"))');
  await type('#archive-query', '尚未保存的日记');
  await click('搜索日记');
  await wait('document.body.textContent.includes("没有找到符合条件的日记")');
  await click('日记');
  if (
    (await evaluate('document.querySelector("#journal-content").value')) !==
      original ||
    (await evaluate('document.querySelector("#entry-date").value')) !==
      '2001-02-03'
  )
    throw new Error('Archive navigation lost unsaved Markdown or date');
  await click('保存日记');
  await wait('Boolean(document.querySelector("article.entry-card"))');
  const first = await api(
    'return (await (await fetch("/api/v1/entries")).json()).items[0];',
  );
  if (first.content_md !== original || first.entry_date !== '2001-02-03')
    throw new Error('Markdown/date changed during composition save');
  await click('编辑');
  const draft = original + '我的草稿\n';
  await type('#journal-content', draft);
  await api(
    `const response = await fetch('/api/v1/auth/login', { method:'POST', headers:{'Content-Type':'application/json','X-LifeArchive-Request':'1'}, body:JSON.stringify({username:${JSON.stringify(username)},password:${JSON.stringify(password)}}) }); if (response.status !== 200) throw Error('Session rotation failed');`,
  );
  await click('保存修改');
  await wait('document.body.textContent.includes("安全校验未通过")');
  if (
    (await evaluate('document.querySelector("#journal-content").value')) !==
    draft
  )
    throw new Error('Session rotation lost draft');
  await click('重新验证登录');
  await wait(
    '[...document.querySelectorAll("button")].some(item => item.textContent.trim() === "重新验证登录" && !item.disabled)',
  );
  await api(
    `const session = await (await fetch('/api/v1/auth/me')).json(); const response = await fetch('/api/v1/entries/${first.id}', { method:'PATCH', headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token}, body:JSON.stringify({expected_revision:1,content_md:'来自另一个窗口'}) }); if (response.status !== 200) throw Error('Concurrent edit failed');`,
  );
  await click('保存修改');
  await wait('document.body.textContent.includes("这篇日记已有新的版本")');
  if (
    (await evaluate('document.querySelector("#journal-content").value')) !==
    draft
  )
    throw new Error('Conflict lost draft');
  await click('读取最新版本');
  await wait('document.body.textContent.includes("服务器版本 2")');
  await click('保留草稿，基于新版继续');
  await click('保存修改');
  await wait('document.querySelector("#journal-content").value === ""');
  await click('修订历史');
  await wait(
    'document.querySelectorAll(".revision-history article").length === 3',
  );
  if (await evaluate('window.__unsafe === true'))
    throw new Error('Unsafe Markdown executed');
  console.log(
    'PASS: real login, IME, raw Markdown/date, rotated session recovery, 409 draft recovery and revision UI',
  );
  await click('日历');
  await wait('Boolean(document.querySelector("#calendar-date"))');
  await selectCalendarDate('2001-02-03');
  await wait(
    'Boolean(document.querySelector(\'button[aria-label="2001-02-03，1 篇日记"]\'))',
  );
  await wait(
    `document.querySelector('section[aria-label="2001-02-03 的日记"] pre')?.textContent === ${JSON.stringify(draft)}`,
  );
  await selectCalendarDate('2001-02-04');
  await wait(
    'document.querySelector(\'section[aria-label="2001-02-04 的日记"]\')?.textContent.includes("这一天还没有日记")',
  );
  await selectCalendarDate('2001-02-03');
  await wait(
    `document.querySelector('section[aria-label="2001-02-03 的日记"] pre')?.textContent === ${JSON.stringify(draft)}`,
  );
  if (await evaluate('window.__unsafe === true'))
    throw new Error('Day view executed unsafe Markdown');
  console.log(
    'PASS: calendar preserves draft, counts backdated journal, reads raw day Markdown and handles empty days',
  );
  await selectCalendarDate('2026-02-03');
  await click('展开往年这一天');
  await wait(
    `document.querySelector('article.on-this-day-entry pre')?.textContent === ${JSON.stringify(draft)}`,
  );
  if (
    (await evaluate(
      'document.querySelector("article.on-this-day-entry time")?.dateTime',
    )) !== '2001-02-03'
  )
    throw new Error('Past-year result lost its original calendar date');
  await selectCalendarDate('2001-02-03');
  await wait('document.body.textContent.includes("往年这一天还没有日记")');
  if (
    await evaluate(
      'Boolean(document.querySelector("article.on-this-day-entry"))',
    )
  )
    throw new Error('On-this-day included the reference year or stale results');
  await selectCalendarDate('2026-02-04');
  await wait('document.body.textContent.includes("往年这一天还没有日记")');
  await selectCalendarDate('2026-02-03');
  await wait(
    `document.querySelector('article.on-this-day-entry pre')?.textContent === ${JSON.stringify(draft)}`,
  );
  const beforeRefresh = onThisDayRequests;
  await wait(
    '[...document.querySelectorAll("button")].some(item => item.textContent.trim() === "刷新日历" && !item.disabled)',
  );
  await click('刷新日历');
  await wait(
    `document.querySelector('article.on-this-day-entry pre')?.textContent === ${JSON.stringify(draft)}`,
  );
  if (
    onThisDayRequests <= beforeRefresh ||
    (await evaluate('window.__unsafe === true'))
  )
    throw new Error('Expanded past-year journals did not refresh safely');
  await click('收起往年这一天');
  if (
    await evaluate(
      'Boolean(document.querySelector("article.on-this-day-entry"))',
    )
  )
    throw new Error('Collapsed past-year content remained mounted');
  console.log(
    'PASS: lazy past-year view preserves full original date/Markdown, excludes same year, switches dates and refreshes',
  );
  await click('归档');
  await searchArchive();
  await wait(
    `document.querySelector('article.archive-entry pre')?.textContent === ${JSON.stringify(draft)}`,
  );
  const submittedRequests = searchRequests;
  await type('#archive-query', '没有这段文字');
  if (
    (await evaluate(
      'document.querySelector("article.archive-entry pre")?.textContent',
    )) !== draft ||
    searchRequests !== submittedRequests
  )
    throw new Error(
      'Editing search inputs changed submitted results or sent a request',
    );
  await click('搜索日记');
  await wait('document.body.textContent.includes("没有找到符合条件的日记")');
  await searchArchive();
  await wait(
    `document.querySelector('article.archive-entry pre')?.textContent === ${JSON.stringify(draft)}`,
  );
  if (
    unsafeSearchTransport ||
    (await evaluate('Boolean(location.search) || window.__unsafe === true'))
  )
    throw new Error('Search exposed a query in the URL or executed Markdown');
  console.log(
    'PASS: private body-only search, Chinese/date filters, submitted filter snapshot and raw Markdown',
  );
  for (const [name, width, height, mobile] of [
    ['desktop', 1440, 1000, false],
    ['mobile', 390, 844, true],
  ]) {
    await cdp('Emulation.setDeviceMetricsOverride', {
      width,
      height,
      deviceScaleFactor: 1,
      mobile,
    });
    for (const view of ['日历', '归档', '日记']) {
      await click(view);
      if (view === '日历') {
        await selectCalendarDate('2026-02-03');
        await click('展开往年这一天');
        await wait(
          `document.querySelector('article.on-this-day-entry pre')?.textContent === ${JSON.stringify(draft)}`,
        );
      }
      if (view === '归档') {
        await searchArchive();
        await wait(
          `document.querySelector('article.archive-entry pre')?.textContent === ${JSON.stringify(draft)}`,
        );
      }
      await evaluate('window.scrollTo(0, 0)');
      const dimensions = await evaluate(
        '({ width:innerWidth, scroll:document.documentElement.scrollWidth })',
      );
      if (dimensions.scroll > dimensions.width)
        throw new Error(`${name} ${view} horizontal overflow`);
      if (process.env.LIFEARCHIVE_BROWSER_ARTIFACT_DIR) {
        await mkdir(process.env.LIFEARCHIVE_BROWSER_ARTIFACT_DIR, {
          recursive: true,
        });
        const screenshot = await cdp('Page.captureScreenshot', {
          format: 'png',
          captureBeyondViewport: false,
        });
        const prefix =
          view === '日历' ? 'calendar-' : view === '归档' ? 'archive-' : '';
        const filename = `${prefix}${name}.png`;
        await writeFile(
          join(process.env.LIFEARCHIVE_BROWSER_ARTIFACT_DIR, filename),
          Buffer.from(screenshot.data, 'base64'),
        );
        if (view === '日历') {
          await evaluate(
            'document.querySelector(\'section[aria-label="往年这一天"]\').scrollIntoView()',
          );
          const pastYearImage = await cdp('Page.captureScreenshot', {
            format: 'png',
            captureBeyondViewport: false,
          });
          await writeFile(
            join(
              process.env.LIFEARCHIVE_BROWSER_ARTIFACT_DIR,
              `on-this-day-${name}.png`,
            ),
            Buffer.from(pastYearImage.data, 'base64'),
          );
        }
      }
      console.log(
        `PASS: ${name} ${view} layout ${width}x${height} without horizontal overflow`,
      );
    }
  }
  allowDialog = true;
  await click('删除');
  await wait('document.querySelectorAll("article.entry-card").length === 0');
  allowDialog = false;
  await click('日历');
  await selectCalendarDate('2001-02-03');
  await wait(
    '[...document.querySelectorAll("button")].some(item => item.textContent.trim() === "刷新日历" && !item.disabled)',
  );
  await click('刷新日历');
  await wait(
    'Boolean(document.querySelector(\'button[aria-label="2001-02-03，0 篇日记"]\'))',
  );
  await wait(
    'document.querySelector(\'section[aria-label="2001-02-03 的日记"]\')?.textContent.includes("这一天还没有日记")',
  );
  console.log(
    'PASS: deleted journal disappears from calendar counts and day detail',
  );
  await selectCalendarDate('2026-02-03');
  await click('展开往年这一天');
  await wait('document.body.textContent.includes("往年这一天还没有日记")');
  if (
    await evaluate(
      'Boolean(document.querySelector("article.on-this-day-entry"))',
    )
  )
    throw new Error('Deleted journal remained in past-year results');
  console.log('PASS: deleted journal disappears from the past-year view');
  await click('归档');
  await searchArchive();
  await wait('document.body.textContent.includes("没有找到符合条件的日记")');
  if (
    await evaluate(
      'document.querySelectorAll("article.archive-entry").length > 0',
    )
  )
    throw new Error('Deleted journal remained in search results');
  if (unsafeSearchTransport || searchRequests < 4)
    throw new Error(
      'Search did not use the expected private request transport',
    );
  await click('退出登录');
  await wait('Boolean(document.querySelector("#username"))');
  if (
    await evaluate(
      'Boolean(document.querySelector("textarea, article.entry-card, #archive-query, article.archive-entry, article.on-this-day-entry")) || localStorage.length > 0 || sessionStorage.length > 0',
    )
  )
    throw new Error('Private state remained after logout');
  if (unexpectedDialog) throw new Error('Unexpected browser dialog');
  console.log(
    'PASS: confirmed deletion, logout clears private UI, no browser storage persistence',
  );
  socket.close();
} finally {
  if (socket?.readyState === WebSocket.OPEN) socket.close();
  chrome.kill('SIGTERM');
}
