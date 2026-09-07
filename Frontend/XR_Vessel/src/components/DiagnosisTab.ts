export const DIAGNOSTIC_CRITERIA = [
    { id: 'AbnormalBeliefs', label: 'Reality Orientation', question: 'Do you ever find yourself noticing patterns or connections that others seem to miss, or feeling that events have a special significance just for you?' },
    { id: 'SocialDetachment', label: 'Interpersonal Resonance', question: 'In social settings, do you feel like an observer rather than a participant, or find that maintaining close bonds feels more exhausting than rewarding?' },
    { id: 'OddBehavior', label: 'Behavioral Idiosyncrasy', question: 'Have you ever been told that your way of speaking, dressing, or reacting to things is notably different from the norm?' },
    { id: 'Impulsivity', label: 'Action Threshold', question: 'How often do you find yourself committed to a decision or action before you\'ve had a chance to weigh the long-term impact?' },
    { id: 'EmotionalInstability', label: 'Affective Regulation', question: 'Do your emotions ever feel like they have a "mind of their own," shifting rapidly in intensity without a clear external cause?' },
    { id: 'FearAbandonment', label: 'Attachment Security', question: 'In your closest relationships, do you often find yourself hyper-aware of signs that the other person might be pulling away or losing interest?' },
    { id: 'Perfectionism', label: 'Cognitive Rigidity', question: 'Do you feel a significant internal distress if things are not arranged "just right" or if a strictly defined routine is interrupted?' },
    { id: 'Anxiety', label: 'Vigilance Level', question: 'Does your body often feel like it\'s in a state of high alert (racing heart, shallow breathing) even when there is no immediate danger?' },
    { id: 'Depression', label: 'Vitality & Interest', question: 'Have you noticed a persistent "graying out" of the world, where things that once sparked joy now feel heavy or indifferent?' },
    { id: 'Psychosis', label: 'Perceptual Boundary', question: 'Do you ever experience sounds, shadows, or sensations that seem vivid to you but aren\'t perceived by those around you?' },
    { id: 'NegativeSymptoms', label: 'Drive & Volition', question: 'Do you struggle with a sense of "emptiness" in your motivation, finding it difficult to start even simple daily tasks?' },
    { id: 'CognitiveImpairment', label: 'Executive Function', question: 'Do you find it increasingly difficult to filter out distractions, follow complex instructions, or hold multiple pieces of information in your mind?' },
    { id: 'Dissociation', label: 'Consciousness Continuity', question: 'Do you ever lose track of time, feel like you\'re watching yourself from a distance, or find that your surroundings suddenly feel "unreal" or dream-like?' }
];

export class DiagnosisTab {
    private static lexiconData: any = null;

    private static async loadLexicon() {
        if (this.lexiconData) return this.lexiconData;
        try {
            const res = await fetch('/lexicon_data.json');
            if (!res.ok) throw new Error('Lexicon fetch failed');
            this.lexiconData = await res.json();
            return this.lexiconData;
        } catch (e) {
            console.error('[Diagnosis] Lexicon load failed:', e);
            return null;
        }
    }

    private static renderHeader(criteria: any[], lexicon: any) {
        return `
            <tr style="background:rgba(0,243,255,0.15);">
                <th style="text-align:left; padding:10px; border-bottom:1px solid var(--border); font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px; white-space:nowrap; width:20%;">Dimension Matrix</th>
                ${criteria.map((c, idx) => `
                    <th data-header-col="${idx}" style="padding:15px 4px; border-bottom:1px solid var(--border); text-align:center; width:5.7%; cursor:help; transition: 0.3s;">
                        <div style="writing-mode:vertical-lr; transform:rotate(180deg); height:140px; white-space:nowrap; margin:0 auto; font-size:0.65rem; padding:10px 0;">${c.label}</div>
                    </th>
                `).join('')}
                <th data-header-col="13" style="padding:15px 4px; border-bottom:1px solid var(--border); width:5.7%; cursor:help; transition: 0.3s;">
                    <div style="writing-mode:vertical-lr; transform:rotate(180deg); height:140px; white-space:nowrap; margin:0 auto; font-size:0.65rem; padding:10px 0;">Genetic</div>
                </th>
            </tr>
        `;
    }

    public static async render(container: HTMLElement, data: any[], onAssess: (results: any) => void) {
        const lexicon = await this.loadLexicon();

        let tableRowsHtml = '';
        data.forEach((row, idx) => {
            const rawDisorder = row.Disorder || 'Unknown';
            const disorderKey = rawDisorder.trim();
            const definition = lexicon?.lexicon[disorderKey] || lexicon?.lexicon[rawDisorder] || `Clinical details for [${disorderKey}] not found in lexicon.`;

            tableRowsHtml += `
                <tr class="diagnosis-row" data-disorder-def="${definition}">
                    <td class="row-label" style="text-align:left; padding:4px 10px; border-bottom:1px solid rgba(255,255,255,0.05); font-family:'Orbitron'; font-size:0.55rem; white-space:nowrap; background:rgba(0,0,0,0.3); border-right:1px solid rgba(255,255,255,0.1); width:20%; transition:0.3s;">${rawDisorder}</td>
                    ${DIAGNOSTIC_CRITERIA.map((c, colIdx) => {
                        const val = row[c.id] || 0;
                        const bg = val === 2 ? 'var(--neon-pink)' : (val === 1 ? 'var(--neon-blue)' : 'transparent');
                        const colDef = lexicon?.criteria[c.label] || 'No definition';
                        return `<td class="matrix-cell" data-col-idx="${colIdx}" data-col-def="${colDef}" style="border:1px solid rgba(255,255,255,0.1); background:${bg}; opacity:0.65; width:5.7%; position:relative;"></td>`;
                    }).join('')}
                    <td class="matrix-cell genetic-cell" data-col-idx="13" data-col-def="Biological predisposition score" style="border:1px solid rgba(255,255,255,0.1); background:${row.Genetic === 2 ? 'var(--neon-pink)' : (row.Genetic === 1 ? 'var(--neon-blue)' : 'transparent')}; opacity:0.65; width:5.7%; text-align:center; position:relative;">
                        ${row.Genetic > 0 ? `<div style="font-size:8px; color:#fff; display:flex; justify-content:center;">${row.Genetic === 2 ? '🧬🧬' : '🧬'}</div>` : ''}
                    </td>
                </tr>
            `;
        });

        container.innerHTML = `
            <div class="diagnosis-container" style="display:flex; flex-direction:column; gap:25px; padding-bottom:120px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div class="breadcrumb">DIAGNOSTIC COMPARISON MATRIX</div>
                    <button id="btn-open-survey" class="neon-btn" style="padding:10px 25px; background:var(--neon-pink); color:#fff; border:none; border-radius:4px; font-family:'Orbitron'; font-size:0.7rem; cursor:pointer; letter-spacing:2px; box-shadow: 0 0 15px var(--neon-pink); font-weight:700;">START SELF-ASSESSMENT TEST</button>
                </div>

                <div class="heatmap-wrapper" style="overflow-x:auto; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); position:relative; max-height:60vh;">
                    <table class="diagnosis-table" style="width:100%; border-collapse:collapse; font-size:0.65rem; color:#fff;">
                        <tbody>
                            ${tableRowsHtml}
                        </tbody>
                        <tfoot style="position: sticky; bottom: 0; z-index: 50; background: #0a0f19; box-shadow: 0 -10px 20px rgba(0,0,0,0.8); border-top: 2px solid var(--neon-blue);">
                            ${this.renderHeader(DIAGNOSTIC_CRITERIA, lexicon)}
                        </tfoot>
                    </table>
                </div>

                <!-- Live Definitions Display -->
                <div style="display:grid; grid-template-columns: 1fr 1.5fr; gap:20px; margin-top:10px;">
                    <div id="live-diagnosis-def" style="background:rgba(255,255,255,0.02); padding:15px; border-radius:8px; border:1px solid rgba(255,0,127,0.2); font-size:0.7rem; min-height:60px;">
                        <span style="color:var(--neon-pink); font-family:'Orbitron'; font-weight:700; display:block; margin-bottom:5px;">DIAGNOSIS DEFINITION</span>
                        <div class="def-text" style="opacity:0.8;">Hover over a row to view clinical details...</div>
                    </div>
                    <div id="live-criteria-def" style="background:rgba(255,255,255,0.02); padding:15px; border-radius:8px; border:1px solid rgba(0,243,255,0.2); font-size:0.7rem; min-height:60px;">
                        <span style="color:var(--neon-blue); font-family:'Orbitron'; font-weight:700; display:block; margin-bottom:5px;">CRITERIA DEFINITION</span>
                        <div class="def-text" style="opacity:0.8;">Hover over a column to view dimension definitions...</div>
                    </div>
                </div>
                
                <div class="table-legend" style="display:flex; gap:15px; margin:10px 0; font-size:0.6rem; opacity:0.6; justify-content:center;">
                    <div style="display:flex; align-items:center; gap:5px;"><div style="width:8px; height:8px; background:var(--neon-pink);"></div> Severe</div>
                    <div style="display:flex; align-items:center; gap:5px;"><div style="width:8px; height:8px; background:var(--neon-blue);"></div> Mild</div>
                    <div style="display:flex; align-items:center; gap:5px;"><div style="width:8px; height:8px; border:1px solid rgba(255,255,255,0.2);"></div> None</div>
                </div>

                <div class="breadcrumb">DIFFERENTIAL ANALYSIS WALKTHROUGH</div>
                <div class="differential-content" style="background:rgba(0, 243, 255, 0.03); padding:25px; border-radius:8px; border:1px solid rgba(0,243,255,0.15); font-size:0.8rem; line-height:1.7; color:rgba(255,255,255,0.9); white-space:pre-wrap; font-family:'Inter', sans-serif;">
                    ${lexicon?.differential || 'Differential data not available.'}
                </div>

                <div class="breadcrumb">FOVEAI EMULATION PROFILE</div>
                <div class="emulation-settings" style="background:rgba(255,255,255,0.02); padding:20px; border-radius:8px; border:1px solid var(--border); display:flex; flex-direction:column; gap:15px;">
                    <p style="font-size:0.75rem; opacity:0.7; font-style:italic;">Choose a psychiatric profile for JEN to emulate, or enable auto-mirroring based on your assessment.</p>
                    
                    <div style="display:flex; gap:20px; align-items:center; flex-wrap:wrap;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <span style="font-size:0.75rem; color:var(--neon-blue); font-family:'Orbitron';">ACTIVE PROFILE:</span>
                            <select id="select-persona" style="background:rgba(0,0,0,0.5); color:#fff; border:1px solid var(--border); padding:5px 10px; border-radius:4px; font-size:0.75rem; font-family:'Orbitron'; outline:none; cursor:pointer;">
                                <option value="Normal">Healthy Baseline (Empathetic/Stable)</option>
                                ${Object.keys(lexicon?.lexicon || {}).filter(k => k !== 'Normal' && k !== 'Genetic').sort().map(k => `
                                    <option value="${k}">${k}</option>
                                `).join('')}
                            </select>
                        </div>
                        
                        <label style="display:flex; align-items:center; gap:10px; cursor:pointer; font-size:0.75rem; color:var(--neon-pink);">
                            <input type="checkbox" id="check-mirror-user" style="width:18px; height:18px; accent-color:var(--neon-pink);">
                            AUTO-MIRROR USER PROFILE (Requires Consent)
                        </label>
                    </div>
                    
                    <div id="persona-description" style="font-size:0.7rem; opacity:0.6; color:var(--neon-blue);">
                        JEN will currently maintain a stable, empathetic baseline.
                    </div>
                </div>

                <!-- Hidden Survey Modal -->
                <div id="survey-modal" style="display:none; position:absolute; top:0; left:0; width:100%; height:100%; background:rgba(10,15,25,0.99); backdrop-filter:blur(35px); z-index:2000; border:1px solid var(--neon-blue); border-radius:4px; flex-direction:column; padding:20px; overflow-y:auto; box-sizing:border-box;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:1px solid var(--border); padding-bottom:15px; flex-shrink:0;">
                        <div class="brand-site-name" style="font-size:1rem; letter-spacing:2px; font-weight:700;">CLINICAL ASSESSMENT</div>
                        <button id="btn-close-survey" style="background:rgba(255,0,127,0.1); border:1px solid var(--neon-pink); color:var(--neon-pink); padding:6px 12px; cursor:pointer; border-radius:4px; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">CLOSE [ESC]</button>
                    </div>
                    <div class="survey-form" style="display:flex; flex-direction:column; gap:20px; width:100%;">
                        <p style="font-size:0.75rem; opacity:0.8; font-style:italic; color:var(--neon-blue); text-align:center; margin-bottom:10px;">Provide accurate pattern markers for hybrid AI profiling. JEN will analyze the cross-sections of your responses.</p>
                        ${DIAGNOSTIC_CRITERIA.map((c, i) => `
                            <div class="survey-item" style="display:flex; flex-direction:column; gap:12px; padding:15px; background:rgba(255,255,255,0.03); border-radius:8px; border:1px solid rgba(255,255,255,0.05); transition:0.3s;">
                                <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-direction:column; gap:10px;">
                                    <div style="font-size:0.8rem; color:var(--neon-blue); font-family:'Orbitron'; font-weight:700;">${i+1}. ${c.label.toUpperCase()}</div>
                                    <div style="display:flex; gap:15px; align-items:center; flex-wrap:wrap;">
                                        <label style="display:flex; align-items:center; gap:6px; cursor:pointer; font-size:0.7rem; color:#fff;">
                                            <input type="radio" name="${c.id}" value="0" checked style="accent-color:var(--neon-blue); width:16px; height:16px;"> NONE
                                        </label>
                                        <label style="display:flex; align-items:center; gap:6px; cursor:pointer; font-size:0.7rem; color:#ff9100;">
                                            <input type="radio" name="${c.id}" value="1" style="accent-color:#ff9100; width:16px; height:16px;"> MILD
                                        </label>
                                        <label style="display:flex; align-items:center; gap:6px; cursor:pointer; font-size:0.7rem; color:var(--neon-pink);">
                                            <input type="radio" name="${c.id}" value="2" style="accent-color:var(--neon-pink); width:16px; height:16px;"> SEVERE
                                        </label>
                                    </div>
                                </div>
                                <div style="font-size:0.75rem; opacity:0.8; line-height:1.4;">${c.question}</div>
                                <textarea id="note-${c.id}" placeholder="Provide specific examples, frequency, or interpersonal context..." style="width:100%; height:80px; background:rgba(0,0,0,0.6); border:1px solid rgba(255,255,255,0.15); color:#fff; font-size:0.75rem; padding:10px; border-radius:6px; outline:none; font-family:'Inter'; resize:vertical;"></textarea>
                            </div>
                        `).join('')}
                        
                        <div class="consent-block" style="background:rgba(0,243,255,0.05); padding:20px; border-radius:8px; border:1px solid var(--neon-blue); margin-top:20px;">
                            <label style="display:flex; gap:15px; cursor:pointer; align-items:flex-start;">
                                <input type="checkbox" id="consent-adaptive" style="width:22px; height:22px; accent-color:var(--neon-blue); margin-top:3px;">
                                <div style="font-size:0.85rem; line-height:1.5; color:#fff;">
                                    <strong style="color:var(--neon-blue); font-family:'Orbitron'; display:block; margin-bottom:5px;">CONSENT FOR ADAPTIVE BEHAVIOR</strong>
                                    I agree to let FOVEAI utilize this diagnostic assessment to adapt its behavior and communication style to my psychiatric profile. 
                                    This data will be used to facilitate a deeper, more supportive connection and optimize my user experience.
                                </div>
                            </label>
                        </div>

                        <button id="btn-submit-assessment" class="neon-btn" style="width:100%; padding:25px; background:var(--neon-blue); color:#000; border:none; border-radius:8px; font-family:'Orbitron'; font-weight:900; letter-spacing:4px; cursor:pointer; transition: 0.3s; margin-top:20px; font-size:1rem; box-shadow:0 0 30px rgba(0,243,255,0.3);">
                            TRANSMIT TO HYBRID BRAIN FOR ANALYSIS
                        </button>
                    </div>
                </div>
            </div>
            <style>
                /* FOVEAI THEME - DIAGNOSIS MATRIX */
                .diagnosis-container {
                    background: linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,243,255,0.02) 100%);
                    font-family: 'Inter', sans-serif;
                }

                .heatmap-wrapper {
                    background: rgba(10, 15, 25, 0.7) !important;
                    border: 1px solid rgba(0, 243, 255, 0.3) !important;
                    box-shadow: 0 0 40px rgba(0,0,0,0.8), inset 0 0 20px rgba(0, 243, 255, 0.05) !important;
                    background-image: linear-gradient(rgba(0, 243, 255, 0.03) 1px, transparent 1px), 
                                      linear-gradient(90deg, rgba(0, 243, 255, 0.03) 1px, transparent 1px) !important;
                    background-size: 20px 20px !important;
                }

                .diagnosis-table {
                    border-collapse: separate !important;
                    border-spacing: 2px !important;
                }

                .row-label {
                    background: rgba(10, 15, 25, 0.9) !important;
                    border-left: 3px solid rgba(0, 243, 255, 0.2) !important;
                    letter-spacing: 1px;
                    font-weight: 500;
                    color: rgba(255, 255, 255, 0.7) !important;
                }

                .matrix-cell {
                    border-radius: 1px;
                    transition: all 0.2s ease-out;
                    border: 1px solid rgba(255,255,255,0.03) !important;
                }

                /* Active Highlighting */
                .diagnosis-row:hover .row-label {
                    background: rgba(0, 243, 255, 0.15) !important;
                    color: #fff !important;
                    border-left: 3px solid var(--neon-pink) !important;
                    text-shadow: 0 0 10px var(--neon-pink);
                    box-shadow: inset 10px 0 20px rgba(255, 0, 127, 0.1);
                }

                .col-highlight {
                    background: rgba(0, 243, 255, 0.2) !important;
                    color: #fff !important;
                    text-shadow: 0 0 15px var(--neon-blue);
                    border-bottom: 2px solid var(--neon-blue) !important;
                }

                .cell-active {
                    outline: 1px solid #fff !important;
                    box-shadow: 0 0 20px #fff, inset 0 0 10px #fff !important;
                    z-index: 100;
                    transform: scale(1.1);
                }

                /* Scrollbar Styling */
                .heatmap-wrapper::-webkit-scrollbar {
                    width: 6px;
                    height: 6px;
                }
                .heatmap-wrapper::-webkit-scrollbar-track {
                    background: rgba(0,0,0,0.3);
                }
                .heatmap-wrapper::-webkit-scrollbar-thumb {
                    background: var(--neon-blue);
                    border-radius: 3px;
                    box-shadow: 0 0 10px var(--neon-blue);
                }

                /* Live Definition Panels */
                #live-diagnosis-def, #live-criteria-def {
                    border: 1px solid rgba(255,255,255,0.1) !important;
                    background: rgba(10, 15, 25, 0.8) !important;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 4px 15px rgba(0,0,0,0.5);
                    position: relative;
                    overflow: hidden;
                }
                
                #live-diagnosis-def::before {
                    content: "";
                    position: absolute;
                    top: 0; left: 0; width: 4px; height: 100%;
                    background: var(--neon-pink);
                    box-shadow: 0 0 10px var(--neon-pink);
                }

                #live-criteria-def::before {
                    content: "";
                    position: absolute;
                    top: 0; left: 0; width: 4px; height: 100%;
                    background: var(--neon-blue);
                    box-shadow: 0 0 10px var(--neon-blue);
                }

                .neon-btn {
                    position: relative;
                    overflow: hidden;
                    border: 1px solid rgba(255, 255, 255, 0.1) !important;
                    transition: 0.4s;
                }
                
                .neon-btn::after {
                    content: "";
                    position: absolute;
                    top: -50%; left: -50%; width: 200%; height: 200%;
                    background: linear-gradient(45deg, transparent, rgba(255,255,255,0.1), transparent);
                    transform: rotate(45deg);
                    transition: 0.8s;
                }

                .neon-btn:hover::after {
                    left: 100%;
                }
            </style>
        `;

        const modal = container.querySelector('#survey-modal') as HTMLElement;
        const btnOpen = container.querySelector('#btn-open-survey');
        const btnClose = container.querySelector('#btn-close-survey');
        const btnSubmit = container.querySelector('#btn-submit-assessment');
        const selectPersona = container.querySelector('#select-persona') as HTMLSelectElement;
        const checkMirror = container.querySelector('#check-mirror-user') as HTMLInputElement;
        const personaDesc = container.querySelector('#persona-description') as HTMLElement;

        const diagDefBox = container.querySelector('#live-diagnosis-def .def-text') as HTMLElement;
        const critDefBox = container.querySelector('#live-criteria-def .def-text') as HTMLElement;
        const footerHeaders = container.querySelectorAll('tfoot th');

        const updatePersona = () => {
            const persona = selectPersona.value;
            if (checkMirror.checked) {
                personaDesc.innerText = "JEN is mirroring your assessment markers.";
                (window as any).localBrain?.setPersona("AUTO-MIRROR");
            } else {
                personaDesc.innerText = `JEN is emulating: ${persona}.`;
                (window as any).localBrain?.setPersona(persona);
            }
        };

        container.querySelectorAll('.matrix-cell').forEach(cell => {
            cell.addEventListener('mouseenter', (e) => {
                const target = e.target as HTMLElement;
                const colIdx = target.getAttribute('data-col-idx');
                const row = target.closest('.diagnosis-row') as HTMLElement;
                
                // Update Definitions
                diagDefBox.innerText = row.getAttribute('data-disorder-def') || '';
                critDefBox.innerText = target.getAttribute('data-col-def') || '';
                
                // Glow Labels
                footerHeaders.forEach(th => {
                    if (th.getAttribute('data-header-col') === colIdx) th.classList.add('col-highlight');
                    else th.classList.remove('col-highlight');
                });
                target.classList.add('cell-active');
            });

            cell.addEventListener('mouseleave', (e) => {
                const target = e.target as HTMLElement;
                target.classList.remove('cell-active');
            });
        });

        selectPersona?.addEventListener('change', updatePersona);
        checkMirror?.addEventListener('change', updatePersona);
        btnOpen?.addEventListener('click', () => modal.style.display = 'flex');
        btnClose?.addEventListener('click', () => modal.style.display = 'none');

        btnSubmit?.addEventListener('click', () => {
            const results: any = {};
            DIAGNOSTIC_CRITERIA.forEach(c => {
                const selected = container.querySelector(`input[name="${c.id}"]:checked`) as HTMLInputElement;
                const note = container.querySelector(`#note-${c.id}`) as HTMLTextAreaElement;
                results[c.id] = { value: parseInt(selected.value), note: note.value.trim() };
            });
            modal.style.display = 'none';
            onAssess(results);
        });
    }
}