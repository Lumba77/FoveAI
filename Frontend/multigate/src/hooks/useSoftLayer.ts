import { useEffect, useRef } from 'react';
import { SoftLayerLoader } from '../softlayer/SoftLayerLoader';

export function useSoftLayer() {
    const softLayerRef = useRef<SoftLayerLoader | null>(null);

    useEffect(() => {
        let isMounted = true;
        if (!softLayerRef.current) {
            const softLayer = new SoftLayerLoader('http://127.0.0.1:8402');
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
