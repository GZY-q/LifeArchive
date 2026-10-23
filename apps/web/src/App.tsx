import { HealthIndicator } from './components/HealthIndicator';

export function App() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        跳到主要内容
      </a>
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="LifeArchive 首页">
          <span className="brand-mark" aria-hidden="true">
            L<span>.</span>
          </span>
          <span>
            <strong>LifeArchive</strong>
            <span className="brand-caption">生活，自有回响。</span>
          </span>
        </a>

        <nav className="navigation" aria-label="主导航">
          <a className="nav-item selected" href="/" aria-current="page">
            <span>首页</span>
            <span className="nav-number" aria-hidden="true">
              01
            </span>
          </a>
          {['日记', '日历', '归档'].map((label) => (
            <button className="nav-item" type="button" disabled key={label}>
              <span>{label}</span>
              <span className="nav-soon">待开放</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <HealthIndicator />
          <p className="edition">LIFEARCHIVE / M0</p>
        </div>
      </aside>

      <main id="main" className="main-content" tabIndex={-1}>
        <header className="page-header">
          <span>你的私人生活档案</span>
          <span className="version-label">起点 · M0</span>
        </header>

        <section className="welcome" aria-labelledby="welcome-title">
          <p className="eyebrow">A PLACE FOR YOUR DAYS</p>
          <h1 id="welcome-title">
            把日子，
            <br />
            慢慢留下。
          </h1>
          <p className="welcome-description">
            为平凡的一天、值得记住的瞬间，
            <br className="desktop-break" />
            留一处可以安心回望的地方。
          </p>
        </section>

        <section className="first-page" aria-labelledby="first-page-title">
          <div className="page-emblem" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <div>
            <p className="eyebrow">故事从这里开始</p>
            <h2 id="first-page-title">为第一篇记录，准备好空间。</h2>
            <p className="first-page-description">
              这里还是档案的第一页。当前提供基础首页与服务连接检查，日记记录将在后续版本开放。
            </p>
          </div>
        </section>

        <footer className="page-footer">
          <span>属于你的记录，由你珍藏。</span>
          <span aria-hidden="true">✳</span>
        </footer>
      </main>
    </div>
  );
}
