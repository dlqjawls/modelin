/**
 * Modelin - Header Bar 컴포넌트
 */
import { Search, Bell } from 'lucide-react';
import { useI18n } from '../hooks/useI18n';
import { useEffect, useRef, useState } from 'react';

function isKrxOpen(date: Date): boolean {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Seoul', weekday: 'short', hour: 'numeric', minute: 'numeric', hour12: false,
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const minutes = Number(values.hour) * 60 + Number(values.minute);
  return !['Sat', 'Sun'].includes(values.weekday) && minutes >= 540 && minutes < 930;
}

export default function HeaderBar() {
  const { t } = useI18n();
  const [searchQuery, setSearchQuery] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, []);

  const isMarketOpen = isKrxOpen(new Date());

  return (
    <header className="header-bar">
      <div className="header-search">
        <Search size={16} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
        <input
          ref={searchInputRef}
          type="text"
          aria-label={t('common.search')}
          placeholder={t('common.search')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <kbd className="keyboard-hint">
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
