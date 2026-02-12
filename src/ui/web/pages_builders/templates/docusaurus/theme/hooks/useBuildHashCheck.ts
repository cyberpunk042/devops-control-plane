import { useEffect } from 'react';

/**
 * Check the current build hash against localStorage.
 * When a new deployment is detected, clear all caches so users
 * see fresh content immediately.
 */
export function useBuildHashCheck(currentHash: string) {
    useEffect(() => {
        const stored = localStorage.getItem('build_hash');
        if (stored && stored !== currentHash) {
            console.log('[Build] New version detected, clearing caches…');
            localStorage.clear();
            sessionStorage.clear();
            if ('caches' in window) {
                caches.keys().then((keys) => keys.forEach((k) => caches.delete(k)));
            }
        }
        localStorage.setItem('build_hash', currentHash);
    }, [currentHash]);
}
