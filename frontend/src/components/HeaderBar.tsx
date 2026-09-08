/**
 * Modelin - Header Bar 컴포넌트
 */
import { Search, Bell } from 'lucide-react';
import { useI18n } from '../hooks/useI18n';
import { useState } from 'react';

export default function HeaderBar() {
  const { t } = useI18n();
  const [searchQuery, setSearchQuery] = useState('');

  // 시장 시간 체크 (KRX: 9:00~15:30 KST)
  const now = new Date();
  const hours = now.getHours();
  const isMarketOpen = hours >= 9 && hours < 16; // 대략적 판단

  return (
    <header className="header-bar">
      <div className="header-search">
        <Search size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
        <input
          type="text"
          placeholder={t('common.search')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <kbd
          style={{
            fontSize: '0.65rem',
            padding: '2px 6px',
            borderRadius: '4px',
            background: 'var(--bg-primary)',
            color: 'var(--text-muted)',
            border: '1px solid var(--border-subtle)',
            whiteSpace: 'nowrap',
          }}
        >
          ⌘K
        </kbd>
      </div>

      <div className="header-actions">
        <div className={`market-indicator ${isMarketOpen ? 'open' : 'closed'}`}>
          <span className="market-indicator-dot" />
          {isMarketOpen ? 'KRX Open' : 'KRX Closed'}
        </div>

        <button className="header-action-btn" title="Notifications">
          <Bell size={16} />
        </button>
      </div>
    </header>
  );
}
