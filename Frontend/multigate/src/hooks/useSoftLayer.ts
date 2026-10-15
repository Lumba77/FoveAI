import { useEffect, useRef } from 'react';
import { SoftLayerLoader } from '../softlayer/SoftLayerLoader';

export function useSoftLayer() {
    const softLayerRef = useRef<SoftLayerLoader | null>(null);

    useEffect(() => {
        let isMounted = true;
        if (!softLayerRef.current) {
            // SoftLayer is decorative: a missing module must never stop the app booting.
            const softLayer = new SoftLayerLoader(window.location.origin);
            softLayerRef.current = softLayer;
            (window as any).foveaiSoftLayer = softLayer;
            
            softLayer.init().then(() => {
                if (isMounted) {
                    softLayer.startUpdateLoop();
                }
            }).catch(e => {
                console.warn('[SoftLayer] Init failed:', e);
            });
        }

        return () => {
            isMounted = false;
        };
    }, []);

    return softLayerRef.current;
}
