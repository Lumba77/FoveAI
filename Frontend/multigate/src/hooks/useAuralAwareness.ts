import { useEffect, useRef } from 'react';
import { auralAwareness, AuralAwareness } from '../senses/AuralAwareness';

export function useAuralAwareness() {
    const audioRef = useRef<AuralAwareness | null>(null);

    useEffect(() => {
        if (!audioRef.current) {
            audioRef.current = auralAwareness;
            (window as any).foveaiAudio = audioRef.current;
        }

        return () => {
            // cleanup if needed
        };
    }, []);

    return audioRef.current;
}
