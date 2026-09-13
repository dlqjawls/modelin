
import { useState, type ReactNode } from 'react';
import { I18nContext, translations, type Lang, type TranslationKey } from './i18n-context';

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>('ko');

  const t = (key: TranslationKey): string => {
    return translations[lang][key] || key;
  };

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

