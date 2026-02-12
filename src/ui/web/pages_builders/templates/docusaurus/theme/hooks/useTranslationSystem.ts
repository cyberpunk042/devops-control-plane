import { useEffect } from 'react';

/**
 * useTranslationSystem Hook
 *
 * Comprehensive Google Translate integration:
 * 1. SPA navigation: hide during translation, show when done
 * 2. Navbar link caching: cache translated links to localStorage
 * 3. Google Translate script loader + hidden widget init
 *
 * Ported from system-course reference implementation.
 */
export function useTranslationSystem(): void {
    // =========================================================================
    // Translation-aware navigation: hide during translation, show when done
    // =========================================================================
    useEffect(() => {
        if (typeof window === 'undefined') return;
        if (!document.cookie.includes('googtrans=')) return;

        let bodyObserver: MutationObserver | null = null;
        let contentObserver: MutationObserver | null = null;
        let debounceTimer: ReturnType<typeof setTimeout> | null = null;
        let fallbackTimer: ReturnType<typeof setTimeout> | null = null;

        const getContainer = () => {
            return document.querySelector('[class*="docMainContainer"]') ||
                document.querySelector('main');
        };

        const createOverlay = () => {
            let loadingEl = document.getElementById('translation-loading-overlay');
            if (!loadingEl) {
                loadingEl = document.createElement('div');
                loadingEl.id = 'translation-loading-overlay';
                loadingEl.innerHTML = '<div class="translation-loading-dots">• • •</div>';
                loadingEl.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;background:transparent;z-index:9999;';
                document.body.appendChild(loadingEl);
            }
        };

        const removeOverlay = () => {
            const loadingEl = document.getElementById('translation-loading-overlay');
            if (loadingEl) loadingEl.remove();
        };

        const cleanup = () => {
            if (bodyObserver) { bodyObserver.disconnect(); bodyObserver = null; }
            if (contentObserver) { contentObserver.disconnect(); contentObserver = null; }
            if (debounceTimer) clearTimeout(debounceTimer);
            if (fallbackTimer) clearTimeout(fallbackTimer);
        };

        const hideAndWatchForTranslation = () => {
            // Show overlay immediately
            createOverlay();

            // Watch body for new containers being added (after SPA navigation)
            bodyObserver = new MutationObserver(() => {
                const newContainer = getContainer();

                // Check if we found a container and haven't observed it yet
                if (newContainer && !newContainer.hasAttribute('data-translation-observed')) {
                    // Mark it so we don't re-observe
                    newContainer.setAttribute('data-translation-observed', 'true');

                    // Hide the NEW container
                    (newContainer as HTMLElement).style.visibility = 'hidden';

                    // Stop watching body, start watching the new container for translation
                    if (bodyObserver) bodyObserver.disconnect();

                    // Observe the NEW container for translation completion
                    contentObserver = new MutationObserver(() => {
                        if (debounceTimer) clearTimeout(debounceTimer);
                        debounceTimer = setTimeout(() => {
                            // Translation done - show content and clean up
                            (newContainer as HTMLElement).style.visibility = 'visible';
                            newContainer.removeAttribute('data-translation-observed');
                            // Signal that translation is ready
                            document.documentElement.classList.add('translation-ready');
                            removeOverlay();
                            cleanup();
                        }, 200);
                    });

                    contentObserver.observe(newContainer, {
                        childList: true,
                        subtree: true,
                        characterData: true
                    });
                }
            });

            bodyObserver.observe(document.body, { childList: true, subtree: true });

            // Fallback: always show after 3 seconds
            fallbackTimer = setTimeout(() => {
                const container = getContainer();
                if (container) {
                    (container as HTMLElement).style.visibility = 'visible';
                    container.removeAttribute('data-translation-observed');
                }
                // Signal that translation is ready (fallback)
                document.documentElement.classList.add('translation-ready');
                removeOverlay();
                cleanup();
            }, 3000);
        };

        const handleLinkClick = (e: Event) => {
            const link = (e.target as HTMLElement).closest('a[href]');
            const href = link?.getAttribute('href');

            // Only handle actual navigation (not same-page or anchor links)
            if (link && href && !href.startsWith('#') && href !== window.location.pathname) {
                // Reset translation-ready so next translation will wait
                document.documentElement.classList.remove('translation-ready');
                hideAndWatchForTranslation();
            }
        };

        // Listen for link clicks (capture phase to run before navigation)
        document.addEventListener('click', handleLinkClick, true);

        return () => {
            document.removeEventListener('click', handleLinkClick, true);
            cleanup();
        };
    }, []);

    // =========================================================================
    // Inject Google Translate script once
    // =========================================================================
    useEffect(() => {
        if (typeof window === 'undefined') return;
        if (document.getElementById('google-translate-script')) return;

        // Navbar caching functions - cache link texts, not innerHTML
        const getNavbarLang = (): string | null => {
            const match = document.cookie.match(/googtrans=\/en\/(\w+(-\w+)?)/);
            return match ? match[1] : null;
        };

        const cacheNavbarLinks = () => {
            const lang = getNavbarLang();
            if (!lang) return;

            const links: Record<string, string> = {};
            document.querySelectorAll('.navbar__link, .navbar__item > a, .navbar a[href]').forEach(link => {
                const href = link.getAttribute('href');
                const text = link.textContent?.trim();
                if (href && text) {
                    links[href] = text;
                }
            });

            try {
                localStorage.setItem(`navbar_links_${lang}`, JSON.stringify(links));
            } catch (e) {
                console.warn('Failed to cache navbar links:', e);
            }
        };

        const script = document.createElement('script');
        script.id = 'google-translate-script';
        script.src = 'https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
        script.async = true;

        (window as any).googleTranslateElementInit = function () {
            const el = document.getElementById('google_translate_hidden');
            if (el && (window as any).google?.translate) {
                new (window as any).google.translate.TranslateElement({
                    pageLanguage: 'en',
                    autoDisplay: false,
                    layout: (window as any).google.translate.TranslateElement.InlineLayout.SIMPLE,
                }, 'google_translate_hidden');

                // Watch for translation to complete (mutations stop)
                const article = document.querySelector('article') || document.querySelector('main') || document.body;
                let translationDebounce: ReturnType<typeof setTimeout>;
                const startTime = Date.now();
                const MIN_TRANSLATION_TIME = 800; // Minimum time before considering translation ready
                const DEBOUNCE_TIME = 400; // No mutations for this long = translation done

                const markTranslationReady = () => {
                    document.documentElement.classList.remove('translation-active');
                    document.documentElement.classList.add('translation-ready');

                    // Cache the translated navbar links for React component to use
                    cacheNavbarLinks();

                    // Add notranslate to prevent GT from interfering on SPA navigation
                    const navbar = document.querySelector('.navbar');
                    if (navbar) {
                        navbar.classList.add('notranslate');
                        navbar.setAttribute('translate', 'no');
                    }

                    translationObserver.disconnect();
                };

                const translationObserver = new MutationObserver(() => {
                    clearTimeout(translationDebounce);
                    translationDebounce = setTimeout(() => {
                        // Mutations stopped - check if minimum time has passed
                        const elapsed = Date.now() - startTime;
                        if (elapsed >= MIN_TRANSLATION_TIME) {
                            markTranslationReady();
                        } else {
                            // Wait for minimum time, then check again
                            setTimeout(markTranslationReady, MIN_TRANSLATION_TIME - elapsed);
                        }
                    }, DEBOUNCE_TIME);
                });

                translationObserver.observe(article, {
                    childList: true,
                    subtree: true,
                    characterData: true
                });

                // Fallback: if no mutations detected within 3 seconds, assume ready
                setTimeout(() => {
                    if (!document.documentElement.classList.contains('translation-ready')) {
                        document.documentElement.classList.remove('translation-active');
                        document.documentElement.classList.add('translation-ready');
                        cacheNavbarLinks();
                        translationObserver.disconnect();
                    }
                }, 3000);
            }
        };

        document.body.appendChild(script);
    }, []);
}
