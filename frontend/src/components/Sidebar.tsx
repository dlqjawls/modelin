/**
 * Modelin - Sidebar 컴포넌트
 */
import {
  LayoutDashboard,
  ScanSearch,
  FlaskConical,
  CandlestickChart,
  PieChart,
  Bot,
  Settings,
  Globe,
} from 'lucide-react';
import { useI18n } from '../hooks/useI18n';

interface SidebarProps {
  activePage: string;
  onNavigate: (page: string) => void;
}

export default function Sidebar({ activePage, onNavigate }: SidebarProps) {
  const { t, lang, setLang } = useI18n();

  const analysisNav = [
    { id: 'dashboard', icon: LayoutDashboard, label: t('nav.dashboard') },
    { id: 'screener', icon: ScanSearch, label: t('nav.screener') },
    { id: 'backtest', icon: FlaskConical, label: t('nav.backtest') },
    { id: 'chart', icon: CandlestickChart, label: t('nav.chart') },
  ];

  const executionNav = [
    { id: 'portfolio', icon: PieChart, label: t('nav.portfolio') },
    { id: 'trading', icon: Bot, label: t('nav.trading') },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">M</div>
        <div className="sidebar-brand">
          <h1>Modelin</h1>
          <p>Quant Platform</p>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">{t('nav.analysis')}</div>
        {analysisNav.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${activePage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
            aria-current={activePage === item.id ? 'page' : undefined}
            aria-label={item.label}
          >
            <item.icon className="nav-item-icon" />
            <span>{item.label}</span>
          </button>
        ))}

        <div className="nav-section-label nav-section-label-spaced">
          {t('nav.execution')}
        </div>
        {executionNav.map((item) => (
          <button
            key={item.id}
            className={`nav-item ${activePage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
            aria-current={activePage === item.id ? 'page' : undefined}
            aria-label={item.label}
          >
            <item.icon className="nav-item-icon" />
            <span>{item.label}</span>
          </button>
        ))}

        <div className="sidebar-spacer" />

        <button
          className="nav-item"
          onClick={() => setLang(lang === 'ko' ? 'en' : 'ko')}
          aria-label={lang === 'ko' ? 'English' : '한국어'}
        >
          <Globe className="nav-item-icon" />
          <span>{lang === 'ko' ? 'English' : '한국어'}</span>
        </button>

        <button
          className={`nav-item ${activePage === 'settings' ? 'active' : ''}`}
          onClick={() => onNavigate('settings')}
          aria-current={activePage === 'settings' ? 'page' : undefined}
          aria-label={t('nav.settings')}
        >
          <Settings className="nav-item-icon" />
          <span>{t('nav.settings')}</span>
        </button>
      </nav>
    </aside>
  );
}
