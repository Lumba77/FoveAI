class NexusARButton {
    static createButton(renderer, sessionInit = {}) {
        const button = document.createElement('button');
        button.style.display = 'none';

        function showARNotSupported() {
            button.style.display = 'none';
        }

        if ('xr' in navigator) {
            button.id = 'ARButton';
            button.style.display = 'block';
            button.style.position = 'absolute';
            button.style.bottom = '20px';
            button.style.left = 'calc(50% - 50px)';
            button.style.width = '100px';
            button.style.padding = '12px 6px';
            button.style.border = '1px solid #00f3ff';
            button.style.borderRadius = '4px';
            button.style.background = 'rgba(0,0,0,0.5)';
            button.style.color = '#fff';
            button.style.font = 'normal 13px sans-serif';
            button.style.textAlign = 'center';
            button.style.opacity = '0.8';
            button.style.outline = 'none';
            button.style.zIndex = '999';
            button.style.cursor = 'pointer';

            navigator.xr.isSessionSupported('immersive-ar').then((supported) => {
                if (supported) {
                    button.textContent = 'ENTER AR';
                    button.onclick = function () {
                        // Unlock audio context on user gesture
                        if (window.foveaiAudioContext && window.foveaiAudioContext.state === 'suspended') {
                            window.foveaiAudioContext.resume();
                        } else if (!window.foveaiAudioContext) {
                            window.foveaiAudioContext = new (window.AudioContext || window.webkitAudioContext)();
                        }

                        if (currentSession === null) {
                            navigator.xr.requestSession('immersive-ar', sessionInit).then(onSessionStarted);
                        } else {
                            currentSession.end();
                        }
                    };
                } else {
                    showARNotSupported();
                }
            });

            let currentSession = null;

            function onSessionStarted(session) {
                session.addEventListener('end', onSessionEnded);

                renderer.xr.setReferenceSpaceType('local-floor');
                renderer.xr.setSession(session);

                button.textContent = 'EXIT AR';
                currentSession = session;
            }

            function onSessionEnded() {
                currentSession.removeEventListener('end', onSessionEnded);
                button.textContent = 'ENTER AR';
                currentSession = null;
            }
        } else {
            showARNotSupported();
        }

        return button;
    }
}

window.NexusARButton = NexusARButton;
