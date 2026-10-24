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
  { stdio: 'ignore' },
);
let socket;
try {
  let port;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      port = (
        await readFile(join(directory, 'DevToolsActivePort'), 'utf8')
      ).split('\n')[0];
      break;
    } catch {
      await delay(100);
    }
  }
  if (!port) throw new Error('Chrome did not provide a debugging endpoint');
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
      `(() => { const button = [...document.querySelectorAll('button')].find(item => item.textContent.trim() === ${JSON.stringify(label)}); if (!button || button.disabled) throw Error('Button unavailable'); button.click(); })()`,
    );
  }
  async function type(selector, text) {
    await evaluate(
      `(() => { const input = document.querySelector(${JSON.stringify(selector)}); input.focus(); input.select(); })()`,
    );
    await cdp('Input.insertText', { text });
  }
  const api = (expression) => evaluate(`(async () => { ${expression} })()`);
  await cdp('Page.enable');
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
    await evaluate('window.scrollTo(0, 0)');
    const dimensions = await evaluate(
      '({ width:innerWidth, scroll:document.documentElement.scrollWidth })',
    );
    if (dimensions.scroll > dimensions.width)
      throw new Error(`${name} horizontal overflow`);
    if (process.env.LIFEARCHIVE_BROWSER_ARTIFACT_DIR) {
      await mkdir(process.env.LIFEARCHIVE_BROWSER_ARTIFACT_DIR, {
        recursive: true,
      });
      const screenshot = await cdp('Page.captureScreenshot', {
        format: 'png',
        captureBeyondViewport: false,
      });
      await writeFile(
        join(process.env.LIFEARCHIVE_BROWSER_ARTIFACT_DIR, `${name}.png`),
        Buffer.from(screenshot.data, 'base64'),
      );
    }
    console.log(
      `PASS: ${name} layout ${width}x${height} without horizontal overflow`,
    );
  }
  allowDialog = true;
  await click('删除');
  await wait('document.querySelectorAll("article.entry-card").length === 0');
  allowDialog = false;
  await click('退出登录');
  await wait('Boolean(document.querySelector("#username"))');
  if (
    await evaluate(
      'Boolean(document.querySelector("textarea, article.entry-card")) || localStorage.length > 0 || sessionStorage.length > 0',
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
