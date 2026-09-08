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
    { id: 'portfolio', icon: PieChart, label: t('nav.portfolio'), badge: t('common.comingSoon') },
    { id: 'trading', icon: Bot, label: t('nav.trading'), badge: t('common.comingSoon') },
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
          <div
            key={item.id}
            className={`nav-item ${activePage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <item.icon className="nav-item-icon" />
            <span>{item.label}</span>
          </div>
        ))}

        <div className="nav-section-label" style={{ marginTop: '8px' }}>
          {t('nav.execution')}
        </div>
        {executionNav.map((item) => (
          <div
            key={item.id}
            className={`nav-item ${activePage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <item.icon className="nav-item-icon" />
            <span>{item.label}</span>
            {item.badge && <span className="nav-item-badge">{item.badge}</span>}
          </div>
        ))}

        <div style={{ flex: 1 }} />

        <div
          className="nav-item"
          onClick={() => setLang(lang === 'ko' ? 'en' : 'ko')}
        >
          <Globe className="nav-item-icon" />
          <span>{lang === 'ko' ? 'English' : '한국어'}</span>
        </div>

        <div
          className={`nav-item ${activePage === 'settings' ? 'active' : ''}`}
          onClick={() => onNavigate('settings')}
        >
          <Settings className="nav-item-icon" />
          <span>{t('nav.settings')}</span>
        </div>
      </nav>
    </aside>
  );
}
