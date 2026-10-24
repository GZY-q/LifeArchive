import { HealthIndicator } from './components/HealthIndicator';
import { AuthGate } from './auth/AuthGate';

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
          <a className="nav-item selected" href="#main" aria-current="page">
            <span>日记</span>
            <span className="nav-number" aria-hidden="true">
              01
            </span>
          </a>
          {['日历', '归档'].map((label) => (
            <button className="nav-item" type="button" disabled key={label}>
              <span>{label}</span>
              <span className="nav-soon">待开放</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <HealthIndicator />
          <p className="edition">LIFEARCHIVE / M1</p>
        </div>
      </aside>

      <main id="main" className="main-content" tabIndex={-1}>
        <header className="page-header">
          <span>你的私人生活档案</span>
          <span className="version-label">日记 · M1</span>
        </header>

        <AuthGate />

        <footer className="page-footer">
          <span>属于你的记录，由你珍藏。</span>
          <span aria-hidden="true">✳</span>
        </footer>
      </main>
    </div>
  );
}
