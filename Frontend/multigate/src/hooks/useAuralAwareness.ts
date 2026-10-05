import { useEffect, useRef } from 'react';
import { AuralAwareness } from '../senses/AuralAwareness';

export function useAuralAwareness() {
    const audioRef = useRef<AuralAwareness | null>(null);

    useEffect(() => {
        if (!audioRef.current) {
            audioRef.current = new AuralAwareness();
            (window as any).foveaiAudio = audioRef.current;
        }

        return () => {
            // cleanup if needed
        };
    }, []);

    return audioRef.current;
}
