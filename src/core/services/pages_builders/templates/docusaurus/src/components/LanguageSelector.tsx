import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useLocation } from '@docusaurus/router';

// Use 2-letter codes instead of emoji flags for better compatibility
const LANGUAGES = [
    { code: 'en', name: 'English', label: 'EN' },
    { code: 'fr', name: 'Français', label: 'FR' },
    { code: 'es', name: 'Español', label: 'ES' },
    { code: 'de', name: 'Deutsch', label: 'DE' },
    { code: 'it', name: 'Italiano', label: 'IT' },
    { code: 'pt', name: 'Português', label: 'PT' },
    { code: 'zh-CN', name: '中文', label: 'ZH' },
    { code: 'ja', name: '日本語', label: 'JA' },
    { code: 'ko', name: '한국어', label: 'KO' },
    { code: 'ar', name: 'العربية', label: 'AR' },
    { code: 'ru', name: 'Русский', label: 'RU' },
];

export default function LanguageSelector(): JSX.Element | null {
    const [isOpen, setIsOpen] = useState(false);
    const [currentLang, setCurrentLang] = useState('en');
    const [isTranslating, setIsTranslating] = useState(false);
    const [navbarContainer, setNavbarContainer] = useState<HTMLElement | null>(null);
    const location = useLocation();

    // Find navbar container on mount AND watch for DOM changes (sidebar toggle, etc.)
    useEffect(() => {
        const findContainer = () => {
            const container = document.getElementById('navbar-language-selector');
            if (container && container !== navbarContainer) {
                setNavbarContainer(container);
            }
        };

        // Try immediately and after short delays (for SSR hydration)
        findContainer();
        const timer = setTimeout(findContainer, 50);
        const timer2 = setTimeout(findContainer, 150);

        // Use MutationObserver to detect navbar changes (much faster than interval)
        const observer = new MutationObserver(() => {
            findContainer();
        });

        // Watch the navbar for changes
        const navbar = document.querySelector('.navbar');
        if (navbar) {
            observer.observe(navbar, {
                childList: true,
                subtree: true,
                attributes: true
            });
        }

        // Also watch body for navbar sidebar changes
        observer.observe(document.body, {
            childList: true,
            subtree: false,
            attributes: true,
            attributeFilter: ['class']
        });

        return () => {
            clearTimeout(timer);
            clearTimeout(timer2);
            observer.disconnect();
        };
    }, [location.pathname, location.hash]); // Re-run when route OR hash changes

    // Check if we're in translated mode on mount
    useEffect(() => {
        // Check Google Translate cookie
        const match = document.cookie.match(/googtrans=\/en\/(\w+(-\w+)?)/);
        if (match) {
            setCurrentLang(match[1]);
            setIsTranslating(true);
        }
    }, []);

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            if (isOpen && !target.closest('.language-selector')) {
                setIsOpen(false);
            }
        };
        document.addEventListener('click', handleClickOutside);
        return () => document.removeEventListener('click', handleClickOutside);
    }, [isOpen]);

    const handleLanguageChange = (langCode: string) => {
        if (langCode === 'en') {
            // Reset to English - clear the cookie
            document.cookie = 'googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;';
            document.cookie = 'googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=.' + window.location.hostname;
            window.location.reload();
        } else {
            // Set translation cookie and reload
            document.cookie = `googtrans=/en/${langCode}; path=/;`;
            document.cookie = `googtrans=/en/${langCode}; path=/; domain=.${window.location.hostname}`;
            window.location.reload();
        }
        setIsOpen(false);
    };

    const currentLanguage = LANGUAGES.find(l => l.code === currentLang) || LANGUAGES[0];

    // The selector button and dropdown
    const selectorContent = (
        <div className="language-selector notranslate">
            <button
                className="language-selector-button"
                onClick={(e) => {
                    e.stopPropagation();
                    setIsOpen(!isOpen);
                }}
                aria-label="Select language"
                title="Translate page"
            >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="2" y1="12" x2="22" y2="12" />
                    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                </svg>
                <span className="language-label">{currentLanguage.label}</span>
                <span className="language-arrow">{isOpen ? '▲' : '▼'}</span>
            </button>

            {isOpen && (
                <div className="language-dropdown">
                    {LANGUAGES.map((lang) => (
                        <button
                            key={lang.code}
                            className={`language-option ${lang.code === currentLang ? 'active' : ''}`}
                            onClick={() => handleLanguageChange(lang.code)}
                        >
                            <span className="language-label">{lang.label}</span>
                            <span className="language-name">{lang.name}</span>
                        </button>
                    ))}
                    {isTranslating && (
                        <div className="language-notice">
                            <small>Translated by Google</small>
                        </div>
                    )}
                </div>
            )}
        </div>
    );

    // If we have a navbar container, portal into it
    if (!navbarContainer) {
        return null;
    }

    return createPortal(selectorContent, navbarContainer);
}
