import type { ReactNode } from 'react';

import { HealthIndicator } from './HealthIndicator';
import { AppIcon } from './AppIcon';

export function AppFrame({
  children,
  navigation,
  account,
  title,
}: {
  children: ReactNode;
  navigation?: ReactNode;
  account?: ReactNode;
  title?: string;
}) {
  return (
    <div
      className={`app-shell ${navigation ? 'is-authenticated' : 'is-login'}`}
    >
      <a className="skip-link" href="#main">
        跳到主要内容
      </a>
      <aside className="sidebar" aria-label="LifeArchive">
        <a className="brand" href="/" aria-label="LifeArchive 首页">
          <span className="brand-mark">
            <AppIcon name="journal" />
          </span>
          <span>
            <strong>LifeArchive</strong>
            <span className="brand-caption">生活，自有回响。</span>
          </span>
        </a>
        {navigation}
        <div className="sidebar-footer">
          {account}
          <HealthIndicator />
        </div>
      </aside>
      <main id="main" className="main-content" tabIndex={-1}>
        {title && (
          <header className="page-header">
            <h1>{title}</h1>
            <span className="privacy-label">
              <AppIcon name="lock" />
              仅你可见
            </span>
          </header>
        )}
        {children}
        <footer className="page-footer">属于你的记录，由你珍藏。</footer>
      </main>
    </div>
  );
}
