import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import './components/ChatLayout.css';
import AvatarOverlay from './AvatarOverlay';
import IgnitionScreen from './IgnitionScreen';
import { useBackendStatus } from './useBackendStatus';
import { useProfilePicture } from './hooks/useProfilePicture';
import Trackball from './trackball/Trackball';
import { useTraits } from './trackball/useTraits';
import { CanvasTab } from './components/tabs/CanvasTab';
import { ImageEditorTab } from './components/tabs/ImageEditorTab';
import { DNATab } from './components/tabs/DNATab';
import { ImageGalleryTab } from './components/tabs/ImageGalleryTab';
import ThemeMachineTab from './components/tabs/ThemeMachineTab';
import { DiagnosticsTab } from './components/tabs/DiagnosticsTab';
import { AgencyTab } from './components/tabs/AgencyTab';
import { MonetizationTab } from './components/tabs/MonetizationTab';
import { PersonaTab } from './components/tabs/PersonaTab';
import { SoundboardTab } from './components/tabs/SoundboardTab';
import { AudioFxTab } from './components/tabs/AudioFxTab';
import { RoleplayTab } from './components/tabs/RoleplayTab';
import { RemoteTab } from './components/tabs/RemoteTab';
import { NewsTab } from './components/tabs/NewsTab';
import { DevKioskTab } from './components/tabs/DevKioskTab';
import { MindTab } from './components/tabs/MindTab';
import { SystemsTab } from './components/tabs/SystemsTab';
import { NEWS } from './news';
import { SettingsOverlay } from './components/SettingsOverlay';
import { AvatarView } from './components/AvatarView';
import { useAuralAwareness } from './hooks/useAuralAwareness';
import { useSoftLayer } from './hooks/useSoftLayer';

// Vibe IDE — lazy: pulls monaco-editor (~4MB chunk), only paid when the tab opens
const CodeEditorTab = React.lazy(() =>
  import('./components/tabs/CodeEditorTab').then(m => ({ default: m.CodeEditorTab }))
);

interface Message {
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string; // thinking-model chain-of-thought, kept out of content
  divider?: { sessionId: string; title: string };  // session boundary marker
  at?: number;        // epoch ms — stamped on send; rides the thread elbow
}

interface User {
  username: string;
  role: string;
  apiKey?: string;
  firstName?: string;
  lastName?: string;
  aiName?: string;
  profilePicture?: string | null;
  features?: string[];
}

// Avatar-protocol tokens (<emotion:>, <movement:>, <micro:>, <mode:>, <thought:>,
// <think>…</think>, *actions*) belong to the motor/XR/TTS layers — strip them from
// display only. msg.content keeps the raw text so TTS keeps its emotion markers.
function displayText(text: string): string {
  return text
    .replace(/<think(?:ing)?>[\s\S]*?<\/think(?:ing)?>/gi, '')
    .replace(/<thought>[\s\S]*?<\/\s*thought\b[^>]*>?/gi, '')
    .replace(/\(\s*thought\s*:[^)]*\)/gi, '')
    // orphan thought fragments — "(…) </thought" leaks where the model
    // opened a plain paren instead of the proper <thought:> channel
    .replace(/\([^()]*\)\s*<\/\s*thought\b[^>]*>?/gi, '')
    .replace(/<\/?\s*thought\b[^>]*>?/gi, '')
    .replace(/<\/\s*thought\b/gi, '')
    .replace(/<\s*thought\b/gi, '')
    .replace(/<[^>]*>/g, '')
    .replace(/<[^>]*$/g, '')
    .replace(/\*[^*]+\*/g, '')
    .replace(/[ \t]+/g, ' ')
    .trim();
}

// Thought channels stay visible: <thought:…> markers, <thought>…</thought>,
// and <think>/<thinking> blocks are pulled out of the raw stream and rendered
// as dim thought panels, inline where the model emitted them.
function renderAssistantContent(text: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const re = /<think(?:ing)?>([\s\S]*?)<\/think(?:ing)?>|<thought>([\s\S]*?)<\/\s*thought\b[^>]*>?|<thought:([^>]+)>|\(\s*thought\s*:\s*([^)]*)\)/gi;
  let last = 0, m: RegExpExecArray | null, k = 0;
  while ((m = re.exec(text)) !== null) {
    const before = displayText(text.slice(last, m.index));
    if (before) parts.push(<span key={k++}>{before}</span>);
    const thought = displayText(m[1] ?? m[2] ?? m[3] ?? m[4] ?? '').trim();
    if (thought) parts.push(<div key={k++} className="thought-block">{thought}</div>);
    last = m.index + m[0].length;
  }
  const tail = displayText(text.slice(last));
  if (tail) parts.push(<span key={k++}>{tail}</span>);
  return parts;
}

function formatModelName(id: string, name?: string): string {
  if (name) return name;
  if (!id) return id;
  if (id.startsWith('micro_')) {
    const raw = id.replace('micro_', '').replace(/_/g, ' ');
    return `⚡ Micro · ${raw.charAt(0).toUpperCase() + raw.slice(1)}`;
  }
  let s = id.replace(/-(multimodal|instruct|chat|v\d+\.\d+)/gi, '');
  let ext = '';
  if (/\.xrlf$/i.test(s)) ext = ' xrlf';
  if (/\.gguf$/i.test(s)) ext = ' gguf';
  s = s.replace(/\.(xrlf|gguf)$/i, '');
  const parts = s.split('-');
  s = parts.slice(0, 3).join(' ');
  return s.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ') + ext;
}

// Transient subtitles for when chat is hidden but conversation continues
function TransientSubtitles({ messages, visible }: { messages: Message[], visible: boolean }) {
  const [activeMsg, setActiveMsg] = useState<{ role: string, content: string, id: number } | null>(null);
  const [fade, setFade] = useState(false);
  const [pos, setPos] = useState({ top: 85, left: 50 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const { clientX, clientY, view } = e;
      if (!view) return;
      const w = view.innerWidth;
      const h = view.innerHeight;
      
      const isMouseBottom = clientY > h * 0.55;
      const isMouseTop = clientY < h * 0.45;
      const isMouseLeft = clientX < w * 0.35;
      const isMouseRight = clientX > w * 0.65;
      const isMouseCenter = !isMouseLeft && !isMouseRight;

      if (isMouseLeft && isMouseBottom) setPos({ top: 85, left: 80 }); // Dodge menu area -> right
      else if (isMouseRight && isMouseBottom) setPos({ top: 85, left: 35 }); // Dodge bottom right -> mid-left
      else if (isMouseCenter && isMouseBottom) setPos({ top: 15, left: 50 }); // Dodge bottom center -> top center
      else if (isMouseCenter && isMouseTop) setPos({ top: 85, left: 50 }); // Dodge top center -> bottom center
      else setPos({ top: 85, left: 50 }); // Default
    };
    
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  useEffect(() => {
    if (!visible) return;
    const last = messages[messages.length - 1];
    if (last && !last.divider) {
      setActiveMsg({ role: last.role, content: displayText(last.content), id: messages.length });
      setFade(false);
      
      const fadeTimer = setTimeout(() => setFade(true), 4000);
      const hideTimer = setTimeout(() => setActiveMsg(null), 5000);
      
      return () => {
        clearTimeout(fadeTimer);
        clearTimeout(hideTimer);
      };
    }
  }, [messages, visible]);

  if (!visible || !activeMsg || !activeMsg.content.trim()) return null;

  return (
    <div 
      className={`transient-subtitles ${activeMsg.role} ${fade ? 'fade-out' : ''}`}
      style={{ top: `${pos.top}%`, left: `${pos.left}%` }}
    >
      {activeMsg.content}
    </div>
  );
}

function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(() => {
    try {
      const saved = localStorage.getItem('foveai_foveai_user');
      if (saved) {
        const parsed = JSON.parse(saved);
        // A real session token means the account was authenticated — restore it
        // even if persona setup (aiName) hasn't run yet.
        if (parsed.apiKey && parsed.username) return parsed;
        if (parsed.firstName && parsed.aiName) return parsed;
      }
      return null;
    } catch (e) {
      return null;
    }
  });

  // Persona setup shows when an authenticated user hasn't named their AI yet.
  // Derived from currentUser — no separate flag to drift out of sync.
  const showSetup = !!currentUser && !currentUser?.aiName;
  const [ignited, setIgnited] = useState(() => {
    try { return sessionStorage.getItem('foveai_ignited') === '1'; } catch { return false; }
  });
  useEffect(() => {
    try {
      if (ignited) sessionStorage.setItem('foveai_ignited', '1');
      else sessionStorage.removeItem('foveai_ignited');
    } catch { /* private mode */ }
  }, [ignited]);
  const userPic = useProfilePicture(currentUser?.apiKey, 'user');
  const aiPic = useProfilePicture(currentUser?.apiKey, 'ai_persona');
  /* hidden file inputs — click a portrait → pick a new picture inline */
  const userPicInput = useRef<HTMLInputElement>(null);
  const aiPicInput = useRef<HTMLInputElement>(null);
  const pickUserPic = (f: File | null) => { if (f) void userPic.upload(f); };
  const pickAiPic = (f: File | null) => { if (f) void aiPic.upload(f); };

  const backend = useBackendStatus();
  const backendDown = backend.state === 'down' || backend.state === 'offline' || backend.state === 'starting';

  // Persist login state to localStorage. Also mirror the fvs_ session into
  // the fvs_gate cookie — the vite dev server shields /remote-api, /novnc,
  // /rdp and /ignition behind it (verified via /api/auth/me).
  useEffect(() => {
    if (currentUser) {
      localStorage.setItem('foveai_foveai_user', JSON.stringify(currentUser));
      if (currentUser.apiKey?.startsWith('fvs_')) {
        const secure = location.protocol === 'https:' ? '; Secure' : '';
        // Domain=xarel.net lets the same session unlock novnc./metrics. subdomains
        const domain = location.hostname.endsWith('xarel.net') ? '; Domain=xarel.net' : '';
        document.cookie = `fvs_gate=${currentUser.apiKey}; Path=/; SameSite=Lax; Max-Age=${30 * 86400}${secure}${domain}`;
      }
    } else {
      localStorage.removeItem('foveai_foveai_user');
      document.cookie = 'fvs_gate=; Path=/; Max-Age=0';
    }
  }, [currentUser]);

  // Session continuity — each app mount starts a fresh session that inherits
  // the tail of the previous ones, with a named divider between them.
  const [sessionId] = useState(() => `sess-${Date.now().toString(36)}`);
  const [sessionTitles, setSessionTitles] = useState<Record<string, string>>({});
  const [editingSession, setEditingSession] = useState<string | null>(null);

  const [clockTime, setClockTime] = useState('--:--');
  useEffect(() => {
    const timer = setInterval(() => {
      const d = new Date();
      setClockTime(d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0'));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  function classifyByTheme(title: string): string {
    const text = (title || '').toLowerCase();
    if (/ui|theme|icon|button|design|watermark|aesthetic|gradient|style|color|layout/.test(text)) return 'theme_ui';
    if (/architect|system|server|proxy|memory|matrix|sleipnir|backend|database|nedb|foveated/.test(text)) return 'theme_arch';
    if (/code|fix|bug|feature|script|deploy|html|css|js|ts|function|api|endpoint/.test(text)) return 'theme_code';
    return 'theme_gen';
  }
  const [editTitle, setEditTitle] = useState('');
  const titledOnce = useRef(false);
  const historyLoaded = useRef(false);
  const sessionTurns = useRef(0);

  // Load the tail of previous sessions once logged in — the chat "starts
  // where the last one ended", separated by named session dividers.
  useEffect(() => {
    if (!currentUser?.apiKey || historyLoaded.current) return;
    historyLoaded.current = true;
    const auth = { Authorization: `Bearer ${currentUser.apiKey}` };
    (async () => {
      try {
        const r = await fetch('/api/sessions', { headers: auth });
        if (!r.ok) return;
        const data = await r.json();
        const sessions = (data.sessions || []).slice(0, 3);
        const titles: Record<string, string> = {};
        const history: Message[] = [];
        for (const s of sessions) {
          const sid = s.session_id || s.id;
          if (!sid) continue;
          titles[sid] = s.title || `Session ${String(sid).slice(-8)}`;
          const mr = await fetch(`/api/session/messages?session_id=${encodeURIComponent(sid)}`, { headers: auth });
          if (!mr.ok) continue;
          const md = await mr.json();
          const msgs = (md.messages || [])
            .filter((m: any) => m.role === 'user' || m.role === 'assistant')
            .slice(-10)
            .map((m: any): Message => ({
              role: m.role,
              content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
            }));
          if (msgs.length) history.push({ role: 'assistant', content: '', divider: { sessionId: sid, title: titles[sid] } }, ...msgs);
        }
        setSessionTitles(t => ({ ...titles, ...t }));
        // Current session divider caps the loaded history
        history.push({ role: 'assistant', content: '', divider: { sessionId, title: 'New session' } });
        setMessages(history.length > 1 ? history : prev => prev);
      } catch { /* history is best-effort — chat works without it */ }
    })();
  }, [currentUser?.apiKey, sessionId]);

  // Autonomy channel — Jen's background loop (compagent :8405) queues
  // spontaneous messages via <self:message>/<self:brief>/scheduled tasks.
  // Drain the outbox into the chat so she can reach out unprompted.
  // Held while a reply streams — otherwise her interjection collides with it.
  const typingRef = useRef(false);
  useEffect(() => {
    if (!currentUser?.apiKey) return;
    const poll = async () => {
      if (typingRef.current) return;
      try {
        const r = await fetch('/api/agent/messages?limit=10');
        if (!r.ok) return;
        const d = await r.json();
        const list = d.messages || [];
        if (!list.length) return;
        const ids: string[] = [];
        const incoming: Message[] = [];
        for (const m of list) {
          if (!m.message) continue;
          ids.push(String(m.id));
          incoming.push({ role: 'assistant', content: m.message });
        }
        if (incoming.length) setMessages(prev => [...prev, ...incoming]);
        if (ids.length) {
          fetch('/api/agent/messages/mark', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(ids)
          }).catch(() => {});
        }
      } catch { /* soul layer may be down — poll again next tick */ }
    };
    poll();
    const t = setInterval(poll, 45000);
    return () => clearInterval(t);
  }, [currentUser?.apiKey]);

  const commitRename = async (sid: string) => {
    const t = editTitle.trim();
    setEditingSession(null);
    if (!t) return;
    setSessionTitles(prev => ({ ...prev, [sid]: t }));
    try {
      await fetch('/api/session/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${currentUser?.apiKey}` },
        body: JSON.stringify({ session_id: sid, title: t })
      });
    } catch { /* rename is best-effort — local title still updated */ }
  };

  // Setup Form State
  const [firstNameInput, setFirstNameInput] = useState('');
  const [lastNameInput, setLastNameInput] = useState('');
  const [aiNameInput, setAiNameInput] = useState('');
  const [setupError, setSetupError] = useState('');

  // Auth Form State
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [inviteInput, setInviteInput] = useState('');
  const [usernameInput, setUsernameInput] = useState('');
  const [passwordInput, setPasswordInput] = useState('');
  const [authError, setAuthError] = useState('');
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  
  // Chat State
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'Welcome to your private FoveAI Copilot. How can I assist your workflow today?' }
  ]);
  const [activeTab, setActiveTab] = useState('Copilot');
  const [newsOverlay, setNewsOverlay] = useState<number | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  useAuralAwareness();
  useSoftLayer();
  
  useEffect(() => {
    // Expose for Quest 3 controller bindings (Unity WebView bridge)
    (window as any).XRLFSettings = {
      show: () => setShowSettings(true),
      hide: () => setShowSettings(false),
      toggle: () => setShowSettings(prev => !prev)
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.shiftKey && (e.key === 'M' || e.key === 'm')) {
        setShowSettings(prev => !prev);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      delete (window as any).XRLFSettings;
    };
  }, []);

  const [showAvatar, setShowAvatar] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  useEffect(() => { typingRef.current = isTyping; }, [isTyping]);
  const [proxyStatus, setProxyStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [activeSimulation, setActiveSimulation] = useState<any | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    try { return localStorage.getItem('foveai_selected_model') || 'auto'; } catch { return 'auto'; }
  });
  const [availableModels, setAvailableModels] = useState<any[]>([]);
  const [swappingModel, setSwappingModel] = useState<string | null>(null);
  const [dutyInfo, setDutyInfo] = useState<{ mode: string; duty: number } | null>(null);
  const [chatProvider, setChatProvider] = useState<'xrlf_proxy' | 'lmstudio' | 'cloud'>(() => {
    try {
      const saved = localStorage.getItem('foveai_chat_provider');
      return saved === 'cloud' || saved === 'lmstudio' || saved === 'xrlf_proxy' ? saved : 'cloud';
    } catch { return 'cloud'; }
  });

  useEffect(() => { try { localStorage.setItem('foveai_selected_model', selectedModel); } catch {} }, [selectedModel]);
  useEffect(() => { try { localStorage.setItem('foveai_chat_provider', chatProvider); } catch {} }, [chatProvider]);

  // Provider-isolated model fleets
  // XRLF Proxy = default (local XRLF runtime on :8402)
  // LM Studio = local GGUF loader on :1234
  // Cloud = opt-in only (requires API key configured in settings)
  const MODEL_FLEETS: Record<string, { id: string; label: string }[]> = {
    // xrlf_proxy has no static fleet — its picker is populated live from
    // /xrlf/v1/packages (the loadable .xrlf files the runtime can hot-swap).
    xrlf_proxy: [
      { id: '1', label: '⚙️ Gear 1: Ambient RAM (1.5B)' },
      { id: '2', label: '⚙️ Gear 2: Light 4B MTP (Multimodal)' },
      { id: '3', label: '⚙️ Gear 3: Flagship 9B Coder' },
      { id: '4', label: '⚙️ Gear 4: Balanced 12B Nemo' },
      { id: '5', label: '🧠 Gear 5: DeepSeek R1 14B Reasoning (MoQ)' },
      { id: '6', label: '🌿 Gear 6: Sleipnir Mamba-2 Swarm & Companion Weave (:8420)' },
    ],
    lmstudio: [
      { id: 'local-3b', label: '💻 3B' },
      { id: 'local-4b', label: '💻 4B' },
      { id: 'local-7b', label: '💻 7B' },
      { id: 'local-8b', label: '💻 8B' },
      { id: 'local-9b', label: '💻 9B' },
      { id: 'local-12b', label: '💻 12B' },
    ],
    cloud: [
      { id: 'auto',          label: '☁️ Cloud Auto-Route (requires API key)' },
      { id: 'cloud-20b',     label: '☁️ 20B' },
      { id: 'cloud-34b',     label: '☁️ 34B' },
      { id: 'cloud-64b',     label: '☁️ 64B' },
      { id: 'cloud-70b',     label: '☁️ 70B' },
      { id: 'cloud-96b',     label: '☁️ 96B' },
      { id: 'cloud-129b',    label: '☁️ 129B' },
    ],
  };
  const [deepThink, setDeepThink] = useState(true);
  const [contextBudget, setContextBudget] = useState(4000);
  const [compressionLevel, setCompressionLevel] = useState(3);

  // Audio input mode — default directly to Vocal VAD / hands-free on web load
  const [inputMode, setInputMode] = useState<'TXT' | 'PTT' | 'VAD'>(() => {
    const saved = localStorage.getItem('foveai_input_mode');
    return saved === 'TXT' || saved === 'PTT' ? saved : 'VAD';
  });
  const [hasMic, setHasMic] = useState<boolean>(true);
  const [hasSpeaker, setHasSpeaker] = useState<boolean>(true);
  const [audioInputs, setAudioInputs] = useState<{ deviceId: string; label: string }[]>([]);
  const [selectedMicId, setSelectedMicId] = useState<string>(() => localStorage.getItem('foveai_mic_device_id') || '');
  const [isRecording, setIsRecording] = useState(false);
  /* transient speech preview (2026-10-08 user rule): when speaking from
     another tab, the transcription surfaces as a transient bubble by the
     user portrait — the user sees their words being heard. */
  const [transientVoice, setTransientVoice] = useState<string | null>(null);
  const [isProcessingAudio, setIsProcessingAudio] = useState(false);

  /* 2026-10-08 user rule: the portraits are ALWAYS present — they are the
     faces of the conversation, on every tab. Pin defaults ON; 📌 unpins. */
  const [jenPinned, setJenPinned] = useState(true);
  const [activeMode, setActiveMode] = useState<'TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD'>(() => {
    const saved = localStorage.getItem('foveai_input_mode');
    return saved === 'TXT' ? 'TEXT' : saved === 'PTT' ? 'Vocal PTT' : 'Vocal VAD';
  });
  const [pendingMode, setPendingMode] = useState<'TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD' | null>(null);
  
  const interactionModes: ('TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD')[] = [
    'TEXT', 'DICTATE', 'Vocal PTT', 'Vocal VAD', 'Video PTT', 'Video VAD'
  ];

  // Hardware audio device probe: if no mic or no speaker is available, lock to TEXT only
  useEffect(() => {
    const probeAudioDevices = async () => {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
          setHasMic(false);
          setHasSpeaker(false);
          setInputMode('TXT');
          setActiveMode('TEXT');
          return;
        }
        const devices = await navigator.mediaDevices.enumerateDevices();
        const inputs = devices.filter(d => d.kind === 'audioinput').map((d, idx) => ({
          deviceId: d.deviceId,
          label: d.label || `Microphone ${idx + 1}`
        }));
        setAudioInputs(inputs);
        const micFound = inputs.length > 0;
        // If device enumeration lists output devices, check speaker; default true if browser doesn't report audiooutput
        const speakerFound = devices.some(d => d.kind === 'audiooutput') || !devices.some(d => 'kind' in d && d.kind === 'audiooutput');

        setHasMic(micFound);
        setHasSpeaker(speakerFound);

        // Do NOT override browser default on Quest 3 / mobile headsets!
        // On Quest 3, the browser's built-in headset mic is the default device;
        // it only captured silence previously because echoCancellation/noiseSuppression/autoGainControl
        // were enabled by default in getUserMedia({ audio: true }).
        const ua = navigator.userAgent || '';
        const isQuest = /OculusBrowser|Quest|VR/i.test(ua);
        if (!isQuest && inputs.length > 0 && !localStorage.getItem('foveai_mic_device_id')) {
          const preferred = inputs.find(d => /rode|nt-usb|usb|camera|webcam/i.test(d.label));
          if (preferred && preferred.deviceId) {
            setSelectedMicId(preferred.deviceId);
          }
        }

        if (!micFound || !speakerFound) {
          console.warn(`[Hardware] Audio device missing: mic=${micFound}, speaker=${speakerFound}. Defaulting to TEXT mode.`);
          setInputMode('TXT');
          setActiveMode('TEXT');
        }
      } catch (e) {
        console.warn('[Hardware] Could not enumerate audio devices:', e);
      }
    };
    probeAudioDevices();
    if (navigator.mediaDevices?.addEventListener) {
      navigator.mediaDevices.addEventListener('devicechange', probeAudioDevices);
      return () => navigator.mediaDevices.removeEventListener('devicechange', probeAudioDevices);
    }
  }, []);

  const audioHardwareReady = hasMic && hasSpeaker;
  const availableInteractionModeList = audioHardwareReady 
    ? interactionModes 
    : (['TEXT'] as ('TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD')[]);

  const getModeExplanation = (m: string | null) => {
    switch (m) {
      case 'TEXT': return "TEXT MODE: Type messages with your keyboard";
      case 'DICTATE': return "DICTATE MODE: Speak and let AI transcribe to text";
      case 'Vocal PTT': return "VOCAL PTT: Hold ball to record audio, release to send";
      case 'Vocal VAD': return "VOCAL VAD: Hands-free continuous audio chat";
      case 'Video PTT': return "VIDEO PTT: Hold ball to record video, release to send";
      case 'Video VAD': return "VIDEO VAD: Hands-free continuous video chat";
      default: return `Ask ${currentUser?.aiName || 'your AI'} to build something...`;
    }
  };

  const lastRollRef = useRef<number>(0);
  const handleRollStep = (dir: number) => {
    if (inputValue.trim()) return;
    if (!audioHardwareReady) return; // Disallow cycling away from TEXT when audio hardware is missing
    const now = Date.now();
    if (now - lastRollRef.current < 500) return; // Throttle mode change to once every 0.5 second
    lastRollRef.current = now;
    
    setPendingMode(prev => {
       const current = prev || activeMode;
       let idx = availableInteractionModeList.indexOf(current as any) + dir;
       if (idx < 0) idx = availableInteractionModeList.length - 1;
       if (idx >= availableInteractionModeList.length) idx = 0;
       return availableInteractionModeList[idx];
    });
  };

  const handleModeConfirm = () => {
    if (pendingMode) {
      setActiveMode(pendingMode);
      setPendingMode(null);
      if (pendingMode === 'TEXT' || pendingMode === 'DICTATE') setInputMode('TXT');
      else if (pendingMode === 'Vocal PTT' || pendingMode === 'Video PTT') setInputMode('PTT');
      else setInputMode('VAD');
    } else {
      handleSendMessage();
    }
  };

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Open/collapsed state for main category accordions
  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({
    'AGENCY & INTELLIGENCE': true,
    'DEVELOPMENT SUITE': false,
    'SENSES & REVENUE': false,
    'EDUTAINMENT': false
  });

  // Site identity — the app is FoveAI; xarel.net is just where it lives.
  const siteName = 'FoveAI';
  const proxyPort = import.meta.env.VITE_PROXY_PORT || '8400';

  const handleAssimilateDisorder = (disorderRow: any, mode: 'chat' | 'xr') => {
    setActiveSimulation(disorderRow);
    if (mode === 'chat') {
      setActiveTab('Copilot');
    } else {
      const protocol = window.location.protocol;
      const hostname = window.location.hostname;
      window.open(`${protocol}//${hostname}:5176`, '_blank');
    }
  };

  const handleClearSimulation = () => {
    setActiveSimulation(null);
  };
  
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // Check Foveated Memory Proxy Health
  useEffect(() => {
    if (!currentUser) return;
    
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/foveated/health');
        if (res.ok) {
          setProxyStatus('online');
          const data = await res.json();
          if (data && data.voice_enabled !== undefined) {
            localStorage.setItem('foveai_voice_speech', String(data.voice_enabled));
          }
        } else {
          setProxyStatus('offline');
        }
      } catch (e) {
        setProxyStatus('offline');
      }
    };
    
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, [currentUser]);

  // Fetch available models from the active provider
  useEffect(() => {
    if (!currentUser) return;
    const fetchModels = async () => {
      try {
        if (chatProvider === 'cloud') {
          // Cloud models from proxy
          const res = await fetch('/api/foveated/v1/models', {
            headers: { 'Authorization': `Bearer ${currentUser.apiKey || currentUser.username}` }
          });
          if (res.ok) {
            const data = await res.json();
            if (data && data.data) {
              // Dedupe by id — upstream lists can carry duplicates and the
              // picker keys options by id (React hates dupe keys).
              const seen = new Set();
              data.data = data.data.filter((m: any) => m && m.id && !seen.has(m.id) && seen.add(m.id));
              setAvailableModels(data.data);
              // Auto-load: keep a remembered model, else default to the nova
              // swarm's base model when the bridge offers it, else 'auto'.
              setSelectedModel(prev => {
                if (data.data.some((m: any) => m.id === prev)) return prev;
                if (data.data.some((m: any) => m.id === 'nova')) return 'nova';
                return 'auto';
              });
            }
          }
        } else if (chatProvider === 'lmstudio') {
          // LM Studio models from :1234
          const res = await fetch('/api/lmstudio/v1/models');
          if (res.ok) {
            const data = await res.json();
            if (data && data.data) setAvailableModels(data.data);
          }
        } else {
          // XRLF / Local Gear provider — query live 6-gear transmission endpoint
          // from the unified proxy (:8400/api/gears/available).
          const [gearsRes, statusRes, dutyRes] = await Promise.all([
            fetch('/api/gears/available').catch(() => null),
            fetch('/api/residency/status').catch(() => null),
            fetch('/api/duty').catch(() => null)
          ]);

          if (dutyRes && dutyRes.ok) {
            const dData = await dutyRes.json().catch(() => null);
            if (dData) setDutyInfo(dData);
          }

          if (gearsRes && gearsRes.ok) {
            const gearsData = await gearsRes.json();
            const statusData = statusRes && statusRes.ok ? await statusRes.json() : {};
            const activeGear = String(statusData.tier || '');

            const allGears = [
              { id: '1', gear: 1, name: 'Gear 1: Ambient RAM (1.5B)', vram: '0 GB', model: 'qwen2.5-coder-1.5b-instruct' },
              { id: '2', gear: 2, name: 'Gear 2: Light 4B MTP', vram: '~2.9 GB', model: 'qwen3.5-4b-mtp-multimodal-v1.0' },
              { id: '3', gear: 3, name: 'Gear 3: Flagship 9B Coder', vram: '~4.8 GB', model: 'qwen3.5-9b-mtp-v1.0' },
              { id: '4', gear: 4, name: 'Gear 4: Balanced 12B Nemo', vram: '~5.8 GB', model: 'Mistral-Nemo-Instruct-2407-Q3_K_M' },
              { id: '5', gear: 5, name: 'Gear 5: DeepSeek R1 14B Reasoning (MoQ)', vram: '~6.0 GB', model: 'deepseek-r1-distill-qwen-14b-iq3_xs' },
              { id: '6', gear: 6, name: 'Gear 6: Sleipnir Mamba-2 Swarm & Companion Weave (:8420)', vram: '~0.1 GB', model: 'neuron-companion-weave' }
            ];

            const allowedMap = gearsData.allowed_gears || {};
            const lockedMap = gearsData.locked_reasons || {};

            const modelsList = allGears.map(g => {
              const isAllowed = !!allowedMap[g.id];
              const isCurrent = activeGear === g.id || (activeGear === 'idle' && g.id === '1');
              const lockedReason = lockedMap[g.id];
              return {
                id: g.id,
                name: g.name,
                model: g.model,
                active: isCurrent,
                allowed: isAllowed,
                lockedReason: lockedReason,
                label: `${isCurrent ? '● ' : isAllowed ? '○ ' : '🔒 '}${g.name} (${g.vram})${lockedReason ? ' — ' + lockedReason : ''}`
              };
            });

            setAvailableModels(modelsList);
            const curr = modelsList.find(m => m.active);
            if (curr) setSelectedModel(curr.id);
          } else {
            // Fallback to static fleet
            const fleet = MODEL_FLEETS.xrlf_proxy;
            setAvailableModels(fleet.map(m => ({ id: m.id, name: m.label, label: m.label, allowed: true })));
          }
        }
      } catch (e) {
        console.warn('Failed to fetch models', e);
        // Fallback to static fleet
        const fleet = MODEL_FLEETS[chatProvider] || MODEL_FLEETS.xrlf_proxy;
        setAvailableModels(fleet.map(m => ({ id: m.id, object: 'model', owned_by: chatProvider })));
      }
    };
    fetchModels();
  }, [currentUser, chatProvider]);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!usernameInput.trim() || !passwordInput.trim()) return;

    setIsAuthLoading(true);
    setAuthError('');

    try {
      // Register creates the account (bootstrap-open while no users exist,
      // admin-only after); login returns a 30-day fvs_ session token.
      const res = await fetch(`/api/auth/${authMode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: usernameInput.trim(),
          password: passwordInput,
          ...(authMode === 'register' ? { inviteCode: inviteInput.trim() } : {})
        })
      });

      const text = await res.text();
      let data: any;
      try { data = JSON.parse(text); } catch { data = null; }

      if (!res.ok || !data) {
        setAuthError(data?.error || `Authentication failed (${res.status})`);
        return;
      }

      // Register doesn't return a session — follow with a login.
      let session = data;
      if (authMode === 'register' && !data.token) {
        const lr = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: usernameInput.trim(), password: passwordInput })
        });
        const lt = await lr.text();
        try { session = JSON.parse(lt); } catch { session = null; }
        if (!lr.ok || !session?.token) {
          setAuthError(session?.error || 'Account created — please log in');
          setAuthMode('login');
          return;
        }
      }

      const u = session.user || {};
      // Persona merge: server profile first, locally saved persona second —
      // the user must never re-type their name on every login.
      let savedPersona: Partial<User> = {};
      try { savedPersona = JSON.parse(localStorage.getItem('foveai_foveai_user') || '{}'); } catch { /* fresh */ }
      setCurrentUser({
        username: u.username || usernameInput.trim(),
        firstName: u.firstName || savedPersona.firstName || u.displayName || usernameInput.trim(),
        lastName: u.lastName || savedPersona.lastName,
        aiName: u.aiName || savedPersona.aiName,
        profilePicture: u.profilePicture ?? savedPersona.profilePicture ?? null,
        role: u.role === 'admin' ? 'Admin' : 'Member',
        apiKey: session.token,          // every fetch already sends apiKey as Bearer
        features: u.features || [],
      });
      setUsernameInput('');
      setPasswordInput('');
    } catch (err) {
      setAuthError('FoveAI backend unreachable — is the stack running?');
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleLogout = () => {
    // End the server-side session too, if there is one
    if (currentUser?.apiKey?.startsWith('fvs_')) {
      fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${currentUser.apiKey}` },
      }).catch(() => {});
    }
    setCurrentUser(null);
    setMessages([{ role: 'assistant', content: 'Session closed.' }]);
  };

  const handleSetup = (e: React.FormEvent) => {
    e.preventDefault();
    if (!aiNameInput.trim()) {
      setSetupError('Name your AI companion');
      return;
    }
    // Preserve the authenticated session — only persona fields change.
    const newUser: User = {
      ...currentUser!,
      firstName: firstNameInput.trim() || currentUser?.firstName,
      lastName: lastNameInput.trim() || currentUser?.lastName,
      aiName: aiNameInput.trim(),
    };
    setCurrentUser(newUser);
    fetch('/api/auth/profile', {
      method: 'PUT', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${currentUser?.apiKey}` },
      body: JSON.stringify({ firstName: newUser.firstName, lastName: newUser.lastName, aiName: newUser.aiName })
    }).catch(() => { /* offline — localStorage still holds it */ });
    setMessages([{ role: 'assistant', content: `Welcome, ${newUser.firstName}. I am ${newUser.aiName}. How can I help you today?` }]);
    setFirstNameInput('');
    setLastNameInput('');
    setAiNameInput('');
    setSetupError('');
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || !currentUser) return;
    
    const userMsg: Message = { role: 'user', content: inputValue, at: Date.now() };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setTransientVoice(null);
    setIsTyping(true);

    try {
      const recentMessages = messages.filter(m => !m.divider).slice(-15);
      const payloadMessages = activeSimulation ? [
        { role: 'system', content: `[EPHEMERAL CLINICAL SIMULATION: ${activeSimulation.Disorder} | Cluster: ${activeSimulation.Cluster} | MEMORY SHIELD: ACTIVE - DO NOT SAVE TURNS TO PERMANENT MEMORY]` },
        ...recentMessages,
        userMsg
      ] : [...recentMessages, userMsg];

      const response = await fetch('/api/foveated/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.apiKey || currentUser.username}`,
          'X-Session-Id': sessionId,
          'X-Memory-Shield': activeSimulation ? 'true' : 'false',
          'X-Deep-Think': deepThink ? 'true' : 'false',
          'X-Context-Budget': String(contextBudget),
          'X-Compression-Level': String(compressionLevel)
        },
        body: JSON.stringify({
          model: selectedModel,
          session_id: sessionId,
          messages: payloadMessages,
          stream: false,
          // Keep avatar-protocol tags in content — TTS/motor/XR consume them
          // from msg.content; displayText() strips them for the chat pane.
          xrlf_raw: true
        })
      });

      // Robust body decode: any non-JSON reply (proxy quirk, raw text)
      // must surface its true body instead of crashing as a SyntaxError.
      let data: any = null;
      let rawBody = '';
      try {
        rawBody = await response.text();
        data = JSON.parse(rawBody);
      } catch (parseErr) {
        if (data === null) {
          data = {
            choices: [{
              message: {
                role: 'assistant',
                content: rawBody.trim().slice(0, 600) || '(empty reply)',
              },
              index: 0,
              finish_reason: 'raw_non_json_reply',
            }],
            _parse_error: `body was not JSON (status ${response.status}): ${String(parseErr).slice(0, 120)}`,
          };
          console.error('[chat] non-JSON reply body (status ' + response.status + '):', rawBody.slice(0, 2000));
        }
      }
      const msgObj = data.choices?.[0]?.message || {};
      const botReply = msgObj.content || (msgObj.reasoning_content && !msgObj.content ? msgObj.reasoning_content : '');
      const reasoning = msgObj.reasoning_content;
      const fallback = data.error?.message || `Proxy error ${response.status}`;

      setMessages(prev => [...prev, { role: 'assistant', content: botReply || reasoning || fallback, at: Date.now(), ...(reasoning ? { reasoning } : {}) }]);

      // ── Synthesize & Voice Jen's reply via Kokoro TTS & AuralAwareness ──
      if (botReply) {
        const cleanSpoken = botReply
          .replace(/<think>[\s\S]*?<\/think>/gi, '')
          .replace(/```[\s\S]*?```/g, '')
          .replace(/[#*_~`]/g, '')
          .trim();
        if (cleanSpoken && cleanSpoken.length > 1) {
          fetch('/api/kokoro/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: cleanSpoken, voice: 'af_heart', speed: 1.05 })
          })
            .then(async (res) => {
              if (res.ok) {
                const blob = await res.blob();
                const reader = new FileReader();
                reader.onload = () => {
                  const b64 = (reader.result as string).split(',')[1];
                  if (b64) {
                    window.dispatchEvent(new CustomEvent('foveai_play_sound', { detail: { base64: b64, voice: 'jen' } }));
                  }
                };
                reader.readAsDataURL(blob);
              }
            })
            .catch((e) => console.warn('[Jen Voice] TTS playback failed:', e));
        }
      }

      // Auto-title the session once it has a few turns to describe
      sessionTurns.current += 1;
      if (sessionTurns.current === 3 && !titledOnce.current) {
        titledOnce.current = true;
        fetch('/api/session/generate-title', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${currentUser.apiKey}` },
          body: JSON.stringify({ session_id: sessionId })
        })
          .then(r => r.json())
          .then(d => {
            if (d.title && d.title !== 'Empty Session' && d.title !== 'Untitled Session') {
              setSessionTitles(t => ({ ...t, [sessionId]: d.title }));
            }
          })
          .catch(() => {});
      }
    } catch (err) {
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `FoveAI Proxy error (Port ${proxyPort}). Details: ${String(err)}` 
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // XRLF provider: choosing a model shifts gears via POST /api/residency/shift (:8400).
  const handleModelSelect = async (id: string) => {
    setSelectedModel(id);
    if (chatProvider !== 'xrlf_proxy' || id === 'auto') return;
    const gearObj = availableModels.find((m: any) => m.id === id);
    if (!gearObj || gearObj.active) return;

    if (gearObj.allowed === false) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `🔒 **${gearObj.name || id}** is currently locked (${gearObj.lockedReason || 'Insufficient VRAM or Solo access required'}). Choose Gear 1 or 2 while slot 12 training runs.`
      }]);
      const activeOne = availableModels.find((m: any) => m.active);
      if (activeOne) setSelectedModel(activeOne.id);
      return;
    }

    setSwappingModel(id);
    setMessages(prev => [...prev, { role: 'assistant', content: `⚙️ Shifting to **${gearObj.name || `Gear ${id}`}**…` }]);
    try {
      const r = await fetch('/api/residency/shift', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gear: id })
      });
      const jr = await r.json().catch(() => ({}));
      if (!r.ok || jr.error) {
        setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ Gear shift failed: ${jr.error || `HTTP ${r.status}`}` }]);
        const still = availableModels.find((m: any) => m.active);
        if (still) setSelectedModel(still.id);
      } else {
        setAvailableModels(prev => prev.map((m: any) => ({ ...m, active: m.id === id })));
        setMessages(prev => [...prev, { role: 'assistant', content: `✅ Shifted to **${gearObj.name || `Gear ${id}`}** — active on ${jr.port ? `port :${jr.port}` : 'designated port'}.` }]);
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ Gear shift request failed: ${String(e)}` }]);
      const still = availableModels.find((m: any) => m.active);
      if (still) setSelectedModel(still.id);
    } finally {
      setSwappingModel(null);
    }
  };

  // ── VAD mode — hands-free continuous listening over the Whisper bridge ──
  // Records ~3.5s windows, transcribes each, accumulates text, auto-sends
  // after ~2.2s of silence. (jenna-vscode uses SpeechRecognition; Firefox
  // lacks it, so this loops MediaRecorder → /api/soul/stt instead.)
  const sendRef = useRef(handleSendMessage);
  sendRef.current = handleSendMessage;
  const vadSendTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const getAudioConstraints = (): MediaStreamConstraints => ({
    audio: {
      ...(selectedMicId ? { deviceId: { exact: selectedMicId } } : {}),
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    }
  });

  useEffect(() => {
    if (inputMode !== 'VAD' || !currentUser || activeTab !== 'Copilot') return;
    let cancelled = false;
    let recorder: MediaRecorder | null = null;
    let stream: MediaStream | null = null;

    const scheduleAutoSend = () => {
      if (vadSendTimer.current) clearTimeout(vadSendTimer.current);
      vadSendTimer.current = setTimeout(() => sendRef.current(), 2200);
    };

    const run = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia(getAudioConstraints());
      } catch (e) {
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
          });
        } catch (fallbackErr) {
          console.error('VAD mic access denied:', fallbackErr);
          setInputMode('PTT');
          return;
        }
      }
      while (!cancelled) {
        const chunks: Blob[] = [];
        const rec = new MediaRecorder(stream);
        recorder = rec;
        rec.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
        const stopped = new Promise<void>(res => { rec.onstop = () => res(); });
        rec.start();
        setIsRecording(true);
        await new Promise(r => setTimeout(r, 3500));
        if (rec.state !== 'inactive') rec.stop();
        await stopped;
        setIsRecording(false);
        if (cancelled) break;
        const blob = new Blob(chunks, { type: 'audio/webm' });
        if (blob.size < 2000) continue;
        const text = await transcribeAudioBlob(blob);
        if (cancelled) break;
        if (text.trim()) {
          setInputValue(prev => (prev.trim() ? prev.trim() + ' ' : '') + text.trim());
          setTransientVoice(prev => (prev ? prev + ' ' : '') + text.trim());
          scheduleAutoSend();
        }
      }
      stream?.getTracks().forEach(t => t.stop());
    };
    run();
    return () => {
      cancelled = true;
      if (vadSendTimer.current) clearTimeout(vadSendTimer.current);
      try { if (recorder && recorder.state !== 'inactive') recorder.stop(); } catch {}
      stream?.getTracks().forEach(t => t.stop());
      setIsRecording(false);
    };
  }, [inputMode, currentUser, activeTab, selectedMicId]);

  // ----------------------------------------------------
  // RENDER SETUP SCREEN
  // ----------------------------------------------------
  if (showSetup) {
    return (
      <div className="auth-screen">
        <div className="glass-panel auth-card">
          <div className="auth-header">
            <img src="/foveai-logo-light.png" alt="FoveAI" style={{ height: '52px', marginBottom: '4px' }} />
            <p>Configure your profile and AI companion</p>
          </div>
          <form className="auth-form" onSubmit={handleSetup}>
            {setupError && <div className="auth-error" style={{ color: '#ff6b6b', background: 'rgba(255, 107, 107, 0.1)', padding: '10px', borderRadius: '6px', marginBottom: '15px', fontSize: '0.9rem' }}>{setupError}</div>}
            <h3 style={{ margin: '10px 0 5px', color: 'var(--accent-cyan)', fontFamily: 'Orbitron', fontSize: '0.95rem' }}>Configure User</h3>
            <div className="input-group">
              <label>First Name</label>
              <input
                type="text"
                placeholder="Your first name..."
                value={firstNameInput}
                onChange={e => setFirstNameInput(e.target.value)}
                autoFocus
              />
            </div>
            <div className="input-group">
              <label>Last Name</label>
              <input
                type="text"
                placeholder="Your last name..."
                value={lastNameInput}
                onChange={e => setLastNameInput(e.target.value)}
              />
            </div>
            <h3 style={{ margin: '15px 0 5px', color: 'var(--accent-cyan)', fontFamily: 'Orbitron', fontSize: '0.95rem' }}>Configure AI</h3>
            <div className="input-group">
              <label>AI Name</label>
              <input
                type="text"
                placeholder="e.g. Lumax, Aria..."
                value={aiNameInput}
                onChange={e => setAiNameInput(e.target.value)}
              />
            </div>
            <button type="submit" className="btn-primary">Enter</button>
          </form>
        </div>
      </div>
    );
  }

  // ----------------------------------------------------
  // RENDER GATE (ignition) — early return; the main app is
  // NEVER mounted under it. ENTER = real page reload with the
  // armed settings as base (sessionStorage marks the pass).
  // ----------------------------------------------------
  if (!ignited && currentUser) {
    return (
      <IgnitionScreen userName={currentUser?.firstName}
        onEnter={() => { setIgnited(true); location.reload(); }} />
    );
  }

  // ----------------------------------------------------
  // RENDER AUTH SCREEN
  // ----------------------------------------------------
  if (!currentUser) {
    return (
      <div className="auth-screen">
        <div style={{ display: 'flex', gap: '20px', alignItems: 'flex-start', flexWrap: 'wrap', justifyContent: 'center' }}>
        {NEWS.length > 0 && (
          <div className="glass-panel" style={{
            maxWidth: '280px', padding: '18px',
            border: '1px solid rgba(0,243,255,0.2)', borderRadius: '8px',
          }}>
            <div style={{ fontFamily: 'Share Tech Mono', fontSize: '0.6rem', letterSpacing: '2px', color: 'var(--accent-cyan)', marginBottom: '10px' }}>
              📰 NEW THIS WEEK
            </div>
            {NEWS.slice(0, 3).map((n, i) => (
              <div key={i} style={{ marginBottom: '10px' }}>
                <div style={{ fontSize: '0.72rem', color: '#fff', fontWeight: 600 }}>{n.title}</div>
                <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', fontFamily: 'Share Tech Mono' }}>{n.date}</div>
              </div>
            ))}
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', marginTop: '8px' }}>
              Log in → 📰 Latest News for details
            </div>
          </div>
        )}
        <div className="glass-panel auth-card">
          <div className="auth-header">
            <img src="/foveai-logo-light.png" alt="FoveAI" style={{ height: '52px', marginBottom: '4px' }} />
            <p>Intelligence Nexus Portal</p>
            <p style={{ marginTop: '6px' }}>
              <a href="/beta.html" style={{ color: 'var(--accent-cyan)', fontSize: '0.8rem', textDecoration: 'none' }}>
                🧪 What is this? — Beta program info
              </a>
            </p>
          </div>
          
          <form className="auth-form" onSubmit={handleAuth}>
            {authError && <div className="auth-error" style={{ color: '#ff6b6b', background: 'rgba(255, 107, 107, 0.1)', padding: '10px', borderRadius: '6px', marginBottom: '15px', fontSize: '0.9rem' }}>{authError}</div>}
            <div className="input-group">
              <label>Username</label>
              <input 
                id="username"
                name="username"
                type="text" 
                placeholder="Enter unique ID..."
                value={usernameInput}
                onChange={e => setUsernameInput(e.target.value)}
                autoComplete="username"
                autoFocus
                disabled={isAuthLoading}
              />
            </div>
            
            <div className="input-group">
              <label>Password</label>
              <input 
                id="password"
                name="password"
                type="password" 
                placeholder="••••••••"
                value={passwordInput}
                onChange={e => setPasswordInput(e.target.value)}
                autoComplete="current-password"
                disabled={isAuthLoading}
              />
            </div>

            {authMode === 'register' && (
              <div className="input-group">
                <label>Beta Invite Code</label>
                <input
                  id="inviteCode"
                  name="inviteCode"
                  type="text"
                  placeholder="Code from your invitation..."
                  value={inviteInput}
                  onChange={e => setInviteInput(e.target.value)}
                  autoComplete="off"
                  disabled={isAuthLoading}
                />
              </div>
            )}

            <button type="submit" className="btn-primary" disabled={isAuthLoading}>
              {isAuthLoading ? 'Please wait...' : (authMode === 'login' ? 'Authenticate' : 'Register Beta Account')}
            </button>
          </form>
          
          <div style={{ textAlign: 'center', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            {authMode === 'login' ? (
              <p>New tester? <span style={{ color: 'var(--accent-cyan)', cursor: 'pointer' }} onClick={() => { setAuthMode('register'); setAuthError(''); }}>Register here</span></p>
            ) : (
              <p>Already registered? <span style={{ color: 'var(--accent-purple)', cursor: 'pointer' }} onClick={() => { setAuthMode('login'); setAuthError(''); }}>Log in</span></p>
            )}
          </div>

          <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.1)', textAlign: 'center' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '10px' }}>Other Services</p>
            <a 
              href="intent://xarel.net/enter-xr#Intent;package=com.foveai.alicevr;action=android.intent.action.MAIN;category=android.intent.category.LAUNCHER;end" 
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-block',
                background: 'rgba(0, 243, 255, 0.1)',
                border: '1px solid rgba(0, 243, 255, 0.3)',
                color: 'var(--accent-cyan)',
                textDecoration: 'none',
                padding: '8px 16px',
                borderRadius: '20px',
                fontSize: '0.85rem',
                fontWeight: 'bold',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0, 243, 255, 0.2)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(0, 243, 255, 0.1)'; }}
            >
              🕶️ Enter XR Portal
            </a>
          </div>
        </div>
        </div>
      </div>
    );
  }

  // ----------------------------------------------------
  // RENDER FULL-SCREEN Overlays
  // ----------------------------------------------------
  if (activeTab === 'WebVM') {
    // Served same-origin from public/webvm (see vite.config.ts middleware for
    // the COOP/COEP headers CheerpX's SharedArrayBuffer needs).
    return (
      <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', zIndex: 9999, background: '#000' }}>
        <button
          onClick={() => setActiveTab('Copilot')}
          style={{
            position: 'absolute', top: '15px', right: '20px', zIndex: 10000,
            background: 'rgba(0,0,0,0.5)', color: '#fff', border: '1px solid rgba(0, 240, 255, 0.5)',
            padding: '8px 16px', borderRadius: '6px', cursor: 'pointer',
            backdropFilter: 'blur(10px)', fontSize: '14px', fontWeight: 'bold',
            boxShadow: '0 4px 6px rgba(0,0,0,0.3)', transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0, 240, 255, 0.2)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(0,0,0,0.5)'; }}
        >
          ⎋ Exit Fullscreen
        </button>
        <iframe
          src="/webvm/"
          style={{ width: '100%', height: '100%', border: 'none' }}
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
          title="Linux WebVM (In-Browser OS)"
        />
      </div>
    );
  }

  // Shared STT — sends a webm blob to the Whisper bridge, returns transcript
  const transcribeAudioBlob = async (audioBlob: Blob): Promise<string> => {
    try {
      const base64data: string = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve((reader.result as string).split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(audioBlob);
      });
      const response = await fetch('/api/soul/stt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          audio_base64: base64data,
          format: 'audio/webm',
          filename: 'recording.webm'
        })
      });
      if (response.ok) {
        const data = await response.json();
        return data.text || data.transcription || '';
      }
    } catch (e) {
      console.error('STT error:', e);
    }
    return '';
  };

  const startRecording = async () => {
    if (isTyping || isProcessingAudio) return;
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') return;
    try {
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(getAudioConstraints());
      } catch {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
        });
      }
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        setIsProcessingAudio(true);
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach(t => t.stop());

        if (audioBlob.size >= 2000) {
          const text = await transcribeAudioBlob(audioBlob);
          if (text.trim()) {
            setTransientVoice(text.trim());
            /* 2026-10-08 user rule: speech becomes chat bubbles BY ITSELF —
               PTT auto-sends the transcription like VAD does (was: text
               parked in the input, never sent). Value flows through the
               normal send path (inputValue → handleSendMessage). */
            setInputValue(text.trim());
            setTimeout(() => sendRef.current(), 350);
          }
        }
        setIsProcessingAudio(false);
      };

      recorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Microphone access denied:', err);
    }
  };

  const stopRecording = () => {
    const rec = mediaRecorderRef.current;
    if (rec && rec.state !== 'inactive') {
      rec.stop();
    }
    setIsRecording(false);
  };

  const toggleCategory = (title: string) => {
    setOpenCategories(prev => ({ ...prev, [title]: !prev[title] }));
  };

  interface MenuItem {
    id: string;
    label: string;
    icon: string;
    isExternal?: boolean;
    href?: string;
  }
  interface MenuCategory {
    title: string;
    icon: string;
    items: MenuItem[];
  }

  const MENU_CATEGORIES: MenuCategory[] = [
    {
      title: 'AGENCY & INTELLIGENCE',
      icon: '⚡',
      items: [
        { id: 'Mind', label: 'Her Mind', icon: '🧠' },
        { id: 'Agency', label: 'Agency Terminal', icon: '🤖' },
        { id: 'Persona', label: 'Persona & MBTI', icon: '🎭' }
      ]
    },
    {
      title: 'DEVELOPMENT SUITE',
      icon: '🛠️',
      items: [
        { id: 'VibeIDE', label: 'Vibe IDE', icon: '🧑‍💻' },
        { id: 'DevKiosk', label: 'Dev Kiosk (App Forge)', icon: '🔧' },
        { id: 'WebVM', label: 'Linux WebVM (WASM)', icon: '🖥️' }
      ]
    },
    {
      title: 'TOOLS',
      icon: '🧰',
      items: [
        { id: 'ImageEditor', label: 'Image Editor', icon: '🖼️' },
        { id: 'ImageGallery', label: 'Image Gallery', icon: '🖼️' },
        { id: 'ThemeMachine', label: 'Theme Machine', icon: '🎨' },
        { id: 'DNA', label: 'DNA Analysis', icon: '🧬' }
      ]
    },
    {
      title: 'SENSES & REVENUE',
      icon: '📊',
      items: [
        { id: 'Canvas', label: 'Canvas (Dreamscape)', icon: '🎨' },
        { id: 'Soundboard', label: 'Voice & Soundboard', icon: '🔊' },
        { id: 'AudioFx', label: 'Audio FX (PipeWire EQ)', icon: '🎚️' },
        { id: 'Monetization', label: 'Monetization', icon: '💰' }
      ]
    },
    {
      title: 'EDUTAINMENT',
      icon: '🎮',
      items: [
        { id: 'Roleplay', label: 'Roleplay & Scenarios', icon: '🎭' },
        { id: 'Diagnostics', label: 'Diagnostic Matrix', icon: '🔬' },
        { id: 'proxy_stats', label: `Foveated Memory Stats (${proxyPort})`, icon: '📊', isExternal: true, href: '/api/foveated/stats' }
      ]
    },
    {
      title: 'REMOTE ACCESS',
      icon: '📡',
      items: [
        { id: 'Remote', label: 'Remote Console', icon: '🖥️' },
        { id: 'ttyd_terminal', label: 'Remote Access (Web Terminal)', icon: '⌨️', isExternal: true, href: `http://${window.location.hostname}:7681` },
        { id: 'novnc_web', label: 'noVNC Web Desktop', icon: '🌐', isExternal: true, href: '/novnc/vnc.html?autoconnect=true&resize=scale&reconnect=true' },
        { id: 'web_rdp', label: 'Web RDP (Guacamole)', icon: '🪟', isExternal: true, href: '/rdp/' },
        { id: 'sunshine_ui', label: 'Sunshine Web UI', icon: '☀️', isExternal: true, href: `https://${window.location.hostname}:47990` }
      ]
    },
    {
      title: 'SOFTWARE',
      icon: '🧰',
      items: [
        { id: 'VibeIDE', label: 'Vibe IDE', icon: '🧑‍💻' },
        { id: 'prompt_kiosk', label: 'Prompt Kiosk', icon: '⌨️', isExternal: true, href: '/dash/prompt-kiosk.html' },
        { id: 'companion', label: 'Companion', icon: '🫂', isExternal: true, href: '/dash/companion.html' },
        { id: 'launch_page', label: 'Launcher', icon: '🚀', isExternal: true, href: '/dash/launch.html' },
        { id: 'garage', label: 'Garage', icon: '🛻', isExternal: true, href: '/dash/garage/' },
        { id: 'graphtest', label: 'Graph Test', icon: '📊', isExternal: true, href: '/dash/graphtest.html' },
        { id: 'beta_page', label: 'Beta Program', icon: '🧪', isExternal: true, href: '/dash/beta.html' }
      ]
    },
    {
      title: 'SYSTEM',
      icon: '⚙️',
      items: [
        { id: 'Statistics', label: 'Statistics', icon: '📊' },
        { id: 'Services', label: 'Services (Zabbix light)', icon: '🛰️' },
        { id: 'Metrics', label: 'Machine Metrics', icon: '📈' },
        { id: 'Settings', label: 'FoveAI Command', icon: '🎛️' }
      ]
    }
  ];

  // ----------------------------------------------------
  // RENDER DASHBOARD
  // ----------------------------------------------------
  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <aside className={`sidebar${sidebarOpen ? ' open' : ''}`}>
        <div className="sidebar-brand" style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '16px 17.4px 12px' }}>
          {/* FoveAI mark — light variant for the dark sidebar. Files live in
              public/: foveai-mark-light.png (here), foveai-icon.png (favicon),
              foveai-logo{,-light}.png (full wordmark for splash pages). */}
          {/* the true FoveAI logotype — full wordmark (user rule 2026-10-08:
              real logo asset, not styled text) */}
          <img src="/foveai-logo-light.png" alt="FoveAI" style={{ height: '30px', display: 'block',
                   filter: 'drop-shadow(0 0 10px rgba(94,234,212,.25))' }} />
          <h2 style={{ margin: 0, position: 'absolute', left: '-9999px' }}>{siteName}</h2>
          <div
            className={`dot ${proxyStatus === 'online' ? 'online' : 'offline'}`}
            title={proxyStatus === 'online' ? 'Online' : 'Offline'}
            style={{ width: '10px', height: '10px', borderRadius: '50%' }}
          />
        </div>
        
        {/* Tap a nav item → close the drawer (mobile); no-op on desktop.
            Category headers expand in place without closing. */}
        <nav className="nav-menu" onClick={(e) => {
          if ((e.target as HTMLElement).closest('.nav-item, .sub-nav-item')) setSidebarOpen(false);
        }}>
          {/* PRIMARY QUICK START BUTTONS — gap 0: .nav-item's own 2px
              margin-bottom gives the same spacing as the sub-nav items */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0', marginBottom: '4px' }}>
            <button 
              className={`nav-item ${activeTab === 'Copilot' ? 'active' : ''}`}
              onClick={() => setActiveTab('Copilot')}
              style={{ fontWeight: 600 }}
            >
              <span style={{ fontSize: '1.2rem' }}>💬</span> Copilot Chat
            </button>
            <button
              className={`nav-item ${activeTab === 'Memory' ? 'active' : ''}`}
              onClick={() => setActiveTab('Memory')}
              style={{ fontWeight: 600 }}
            >
              <span style={{ fontSize: '1.2rem' }}>🧠</span> Memory Vault
            </button>
            <button
              className={`nav-item ${activeTab === 'News' ? 'active' : ''}`}
              onClick={() => setActiveTab('News')}
              style={{ fontWeight: 600 }}
            >
              <span style={{ fontSize: '1.2rem' }}>📰</span> Latest News
            </button>
          </div>

          <div style={{ height: '1px', background: 'var(--border-glass)', margin: '2px 0 4px 0' }} />

          {/* 4 MAIN CATEGORIES ACCORDION BUTTONS */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            {MENU_CATEGORIES.map((cat) => {
              const isOpen = openCategories[cat.title] ?? true;
              const hasActiveChild = cat.items.some(i => i.id === activeTab);

              return (
                <div key={cat.title} style={{ display: 'flex', flexDirection: 'column' }}>
                  {/* Category Button Header */}
                  <button
                    className={`category-header ${hasActiveChild ? 'has-active' : ''}`}
                    onClick={() => toggleCategory(cat.title)}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span>{cat.icon}</span>
                      <span>{cat.title}</span>
                    </span>
                    <span style={{ fontSize: '0.7rem', opacity: 0.7 }}>
                      {isOpen ? '▾' : '▸'}
                    </span>
                  </button>

                  {/* Inline Expanded Items */}
                  {isOpen && (
                    <div className="category-items">
                      {cat.items.map(item => {
                        if (item.isExternal) {
                          return (
                            <a 
                              key={item.id}
                              href={item.href}
                              target="_blank"
                              rel="noreferrer"
                              className="sub-nav-item"
                              style={{ textDecoration: 'none' }}
                            >
                              <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span>{item.icon}</span> {item.label}
                              </span>
                              <span style={{ fontSize: '0.75rem', opacity: 0.5 }}>↗</span>
                            </a>
                          );
                        }
                        const isActive = activeTab === item.id;
                        return (
                          <button 
                            key={item.id}
                            className={`sub-nav-item ${isActive ? 'active' : ''}`} 
                            onClick={() => setActiveTab(item.id)}
                          >
                            <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span>{item.icon}</span> {item.label}
                            </span>
                            {isActive && <span style={{ fontSize: '0.6rem', color: 'var(--accent-cyan)' }}>●</span>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </nav>

        <div className="user-profile">
          <div className="user-info">
            {/* 2026-10-08: real portrait instead of the redundant initial —
                the picture already starts with the user's face; circular
                crop focuses the center (user rule). */}
            <div className="avatar">
              <img src={userPic.url || currentUser.profilePicture || '/avatars/user_fallback.png'}
                   alt={currentUser.username}
                   onError={(e) => { e.currentTarget.style.display = 'none'; }}
                   style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'center top', borderRadius: '50%' }} />
            </div>
            <div>
              <div className="username">{currentUser.username}</div>
              <div className="role">{currentUser.role}</div>
            </div>
          </div>
          <button className="logout-btn" onClick={handleLogout} title="Log Out">
            ⎋
          </button>
        </div>
      </aside>
      {sidebarOpen && <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />}

      {/* Main Content Area */}
      <main className="main-content">
        {/* Top Bar with Server Metrics & Quick Actions */}
        <header className="chat-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 24px 14px 20px', gap: '22px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {/* Hamburger — only visible under the mobile media query */}
            <button className="icon-btn menu-toggle" title="Menu" onClick={() => setSidebarOpen(!sidebarOpen)}>☰</button>
            {/* Quick Action Toolbar */}
            <div className="topbar-actions" style={{ display: 'flex', gap: '14px' }}>
              {/* clock as a plain chip (not a button) — same padding box as
                  the metrics panel; user rule: the metrics panel is the
                  guiding measurement for the whole top bar */}
              <div
                title="Local Time"
                style={{ display: 'flex', alignItems: 'center', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.1)', fontSize: '0.72rem', padding: '6px 12px', borderRadius: '4px', fontFamily: 'Share Tech Mono', color: 'rgba(255,255,255,0.7)' }}
              >
                {clockTime}
              </div>
              <button
                className={`icon-btn ${showAvatar ? 'active' : ''}`}
                title="Toggle Video / 3D Avatar"
                onClick={() => setShowAvatar(!showAvatar)}
                style={showAvatar ? { background: 'rgba(255, 0, 127, 0.3)', borderColor: 'var(--neon-pink)' } : {}}
              >
                🎥
              </button>
              <button className={`icon-btn ${activeTab === 'Soundboard' ? 'active' : ''}`} title="Voice & Soundboard" onClick={() => setActiveTab('Soundboard')}>
                🔊
              </button>
              <button className={`icon-btn ${activeTab === 'AudioFx' ? 'active' : ''}`} title="Audio FX — PipeWire EQ & mic FX" onClick={() => setActiveTab('AudioFx')}>
                🎚️
              </button>
              <button className={`icon-btn ${deepThink ? 'active' : ''}`} title="Turbo — extra reasoning effort (burns more tokens)" onClick={() => setDeepThink(!deepThink)} style={deepThink ? { color: 'var(--accent-magenta)', textShadow: '0 0 12px rgba(232,182,76,.7)' } : {}}>
                ⚡
              </button>
              <button className={`icon-btn ${activeTab === 'Canvas' ? 'active' : ''}`} title="Creative / Image Canvas" onClick={() => setActiveTab('Canvas')}>
                🎨
              </button>

              <select
                className="context-select"
                title="Context size & compression"
                value={contextBudget}
                onChange={e => {
                  const v = parseInt(e.target.value, 10);
                  setContextBudget(v);
                  setCompressionLevel(v <= 4000 ? 5 : v <= 8192 ? 4 : v <= 16384 ? 3 : v <= 32768 ? 2 : 1);
                }}
                style={{ background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.7)', borderRadius: '4px', padding: '6px 12px', fontSize: '0.72rem', fontFamily: 'Share Tech Mono', cursor: 'pointer' }}
              >
                <option value={4096}>4K Canonical</option>
                <option value={8000}>8K Small</option>
                <option value={16000}>16K Normal</option>
                <option value={32000}>32K Large</option>
                <option value={64000}>64K Max</option>
              </select>
            </div>

            {/* Active Simulation Pill */}
            {activeSimulation && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(0, 243, 255, 0.1)', border: '1px solid #00f3ff', padding: '4px 10px', borderRadius: '4px', fontSize: '0.72rem', color: '#00f3ff', fontWeight: 'bold' }}>
                <span>🎭 SIMULATION: {activeSimulation.Disorder}</span>
                <span style={{ fontSize: '0.65rem', opacity: 0.8, color: '#a0e0ff' }}>(Memory Shield ON)</span>
                <button 
                  onClick={handleClearSimulation} 
                  style={{ background: 'rgba(255, 0, 80, 0.2)', border: '1px solid #ff4d6d', color: '#ff4d6d', borderRadius: '3px', padding: '1px 6px', fontSize: '0.65rem', cursor: 'pointer' }}
                >
                  ⎋ Revert
                </button>
              </div>
            )}
          </div>

          {/* Top Bar Server Metrics — hangs at the AI portrait's left edge,
              never behind her (user: Jen should let it come forward) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px', fontFamily: 'Share Tech Mono', fontSize: '0.7rem', color: 'rgba(255,255,255,0.7)', background: 'rgba(0,0,0,0.4)', padding: '6px 12px', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.1)', marginRight: '168px' }}>
            <div>CPU: <span style={{ color: 'var(--neon-green)' }}>14%</span></div>
            <div>RAM: <span style={{ color: 'var(--neon-green)' }}>3.8 GB</span></div>
            <div>STT: <span style={{ color: 'var(--accent-cyan)' }}>Whisper</span></div>
          </div>
        </header>

      {(jenPinned) && (
        <>
          <div className={`ai-avatar-window ${jenPinned ? 'pinned' : ''}`} title="Click to change the AI portrait">
            <span className="ai-avatar-name">
              {currentUser?.aiName || 'JEN'}
              <span style={{ float: 'right', cursor: 'pointer', opacity: 0.6 }} onClick={(e) => { e.stopPropagation(); setJenPinned(!jenPinned); }} title={jenPinned ? "Unpin avatars" : "Pin avatars to all screens"}>📌</span>
            </span>
            {/* click the portrait → pick a new persona image; falls back to
                the live view; the still overlay uses the persona picture */}
            <div className="avatar-clickable" onClick={() => aiPicInput.current?.click()}>
              {aiPic.url
                ? <img src={aiPic.url} alt={currentUser?.aiName || 'AI'} className="ai-avatar-image"
                    onError={(e) => { e.currentTarget.src = '/avatars/fallback.png'; }} />
                : <AvatarView mode={activeMode.startsWith('Video') ? 'video' : 'still'} />}
            </div>
          </div>
          <div className={`user-avatar-window ${jenPinned ? 'pinned' : ''}`} title="Click to change your portrait">
            <span className="user-avatar-name">{currentUser?.firstName?.toUpperCase() || 'USER'}</span>
            <div className={`avatar-clickable ${isRecording ? 'speaking' : ''}`} onClick={() => userPicInput.current?.click()}
                 title={isRecording ? 'listening…' : 'Click to change your portrait'}>
              <img src={userPic.url || currentUser?.profilePicture || '/avatars/user_fallback.png'} alt="User" className="user-avatar-image" onError={(e) => (e.currentTarget.src = '/avatars/fallback.png')} />
            </div>
          </div>
          {transientVoice && activeTab !== 'Copilot' && (
            <div className="transient-voice-bubble" aria-live="polite">
              “{transientVoice}”
              <span className="tv-send-hint">↗</span>
            </div>
          )}
          <input ref={userPicInput} type="file" accept="image/*" hidden
            onChange={(e) => { pickUserPic(e.target.files?.[0] ?? null); e.target.value = ''; }} />
          <input ref={aiPicInput} type="file" accept="image/*" hidden
            onChange={(e) => { pickAiPic(e.target.files?.[0] ?? null); e.target.value = ''; }} />
          <TransientSubtitles messages={messages} visible={activeTab !== 'Copilot'} />
        </>
      )}
        {/* Tab Router */}
        {activeTab === 'Memory' ? (
          <div style={{ flex: 1, width: '100%', height: '100%', overflow: 'hidden' }}>
            <iframe
              src="/dash/memory"
              style={{ width: '100%', height: '100%', border: 'none', background: '#000' }}
              title="Memory Vault Dashboard"
            />
          </div>
        ) : activeTab === 'Settings' ? (
          <div style={{ flex: 1, width: '100%', height: '100%', overflow: 'hidden' }}>
            {/* FoveAI Command — proxied to the memory dashboard :8401 via vite,
                same-origin so it works on localhost, LAN and the tunnel */}
            <iframe
              src="/settings.html"
              style={{ width: '100%', height: '100%', border: 'none', background: '#0b0f1a' }}
              title="FoveAI Command — Settings & Control"
            />
          </div>
        ) : activeTab === 'Canvas' ? (
          <CanvasTab />
        ) : activeTab === 'ImageEditor' ? (
          <ImageEditorTab />
        ) : activeTab === 'ImageGallery' ? (
          <ImageGalleryTab />
        ) : activeTab === 'DNA' ? (
          <DNATab />
        ) : activeTab === 'ThemeMachine' ? (
          <ThemeMachineTab />
        ) : activeTab === 'Roleplay' ? (
          <RoleplayTab 
            onApplyRole={(role, mode) => handleAssimilateDisorder({ Disorder: role.title, Cluster: 'Roleplay Scenario', systemPrompt: role.systemPrompt }, mode)}
            activeSimulation={activeSimulation}
            onClearSimulation={handleClearSimulation}
          />
        ) : activeTab === 'Diagnostics' ? (
          <DiagnosticsTab 
            onAssimilateDisorder={handleAssimilateDisorder}
            activeSimulation={activeSimulation}
            onClearSimulation={handleClearSimulation}
          />
        ) : activeTab === 'Remote' ? (
          <RemoteTab />
        ) : activeTab === 'Metrics' ? (
          <div style={{ flex: 1, width: '100%', height: '100%', overflow: 'hidden' }}>
            {/* Netdata — real-time machine metrics, proxied same-origin
                to :19999 via vite so it works on LAN and the tunnel */}
            <iframe
              src="/netdata"
              style={{ width: '100%', height: '100%', border: 'none', background: '#0b0f1a' }}
              title="Machine Metrics — Netdata"
            />
          </div>
        ) : activeTab === 'Mind' ? (
          <MindTab />
        ) : activeTab === 'Agency' ? (
          <AgencyTab />
        ) : activeTab === 'Monetization' ? (
          <MonetizationTab />
        ) : activeTab === 'Soundboard' ? (
          <SoundboardTab />
        ) : activeTab === 'AudioFx' ? (
          <AudioFxTab />
        ) : activeTab === 'News' ? (
          <NewsTab />
        ) : activeTab === 'Statistics' ? (
          <div style={{ flex: 1, width: '100%', height: '100%', overflow: 'hidden' }}>
            {/* Foveated Memory dashboard — :8401 public/index.html via /dash */}
            <iframe
              src="/dash/"
              style={{ width: '100%', height: '100%', border: 'none', background: '#0b0f1a' }}
              title="FoveAI Statistics — Memory Dashboard"
            />
          </div>
        ) : activeTab === 'Services' ? (
          <SystemsTab />
        ) : activeTab === 'VibeIDE' ? (
          <React.Suspense fallback={<div style={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', color: '#666' }}>loading editor…</div>}>
            <CodeEditorTab />
          </React.Suspense>
        ) : activeTab === 'DevKiosk' ? (
          <DevKioskTab currentUser={currentUser.username} />
        ) : activeTab === 'Persona' ? (
          <PersonaTab 
            onNavigateToDiagnostics={() => setActiveTab('Diagnostics')}
            activeSimulation={activeSimulation}
            onClearSimulation={handleClearSimulation}
          />
        ) : (
          <>
            {/* Model/provider bar — sits above the chat area, not in the composer */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: '10px',
              padding: '6px 160px 6px 16px', fontFamily: 'Share Tech Mono',
              borderBottom: '1px solid rgba(255,255,255,0.06)',
              flexShrink: 0
            }}>
              <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', letterSpacing: '0.1em' }}>MODEL</span>
              <select
                value={chatProvider}
                onChange={e => {
                  const p = e.target.value as 'xrlf_proxy' | 'lmstudio' | 'cloud';
                  setChatProvider(p);
                  setSelectedModel('auto');
                }}
                disabled={isTyping || !!swappingModel}
                style={{
                  padding: '6px 10px',
                  background: 'rgba(0,0,0,0.4)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  color: '#fff',
                  borderRadius: '6px',
                  fontFamily: 'Share Tech Mono',
                  fontSize: '0.75rem',
                  outline: 'none',
                  cursor: 'pointer'
                }}
                title="Chat Provider"
              >
                <option value="xrlf_proxy">🧠 XRLF Proxy</option>
                <option value="lmstudio">💻 LM Studio</option>
                <option value="cloud">☁️ Cloud</option>
              </select>

              <select
                value={selectedModel}
                onChange={e => handleModelSelect(e.target.value)}
                disabled={isTyping || !!swappingModel}
                style={{
                  padding: '6px 10px',
                  background: 'rgba(0,0,0,0.4)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  color: '#fff',
                  borderRadius: '6px',
                  fontFamily: 'Share Tech Mono',
                  fontSize: '0.8rem',
                  outline: 'none',
                  cursor: 'pointer',
                  maxWidth: '340px'
                }}
                title="Select AI Model — XRLF choices hot-swap the runtime"
              >
                {chatProvider === 'xrlf_proxy' ? (
                  availableModels.map((m: any) => (
                    <option key={m.id} value={m.id} disabled={m.allowed === false}>
                      {m.label || m.name || m.id}
                    </option>
                  ))
                ) : (
                  <>
                    {chatProvider === 'cloud' && <option value="auto">auto (Cloud Auto-Route)</option>}
                    {chatProvider === 'lmstudio' && <option value="auto">auto (Active LM Studio Model)</option>}
                    {(MODEL_FLEETS[chatProvider] || []).map(m => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                    {chatProvider === 'lmstudio' && availableModels.map((m: any) => (
                      <option key={m.id} value={m.id}>{formatModelName(m.id)}</option>
                    ))}
                    {chatProvider === 'cloud' && availableModels.map((m: any) => (
                      <option key={m.id} value={m.id}>{formatModelName(m.id)}</option>
                    ))}
                  </>
                )}
              </select>

              {swappingModel && (
                <span style={{ fontSize: '0.7rem', color: 'var(--accent-cyan)' }}>
                  ⏳ loading {swappingModel}…
                </span>
              )}

              {dutyInfo && dutyInfo.mode === 'manual' && dutyInfo.duty === 100 && (
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  fontSize: '0.7rem', background: 'rgba(255, 170, 0, 0.15)',
                  border: '1px solid rgba(255, 170, 0, 0.4)',
                  padding: '3px 8px', borderRadius: '4px', color: '#ffb300'
                }}>
                  ⚠️ GPU Pinned at Manual 100%
                  <button
                    onClick={async () => {
                      try {
                        const r = await fetch('/api/duty', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ mode: 'auto' })
                        });
                        if (r.ok) {
                          const d = await r.json();
                          setDutyInfo(d);
                          fetchModels();
                        }
                      } catch {}
                    }}
                    style={{
                      background: 'rgba(255, 170, 0, 0.3)', border: 'none',
                      color: '#fff', borderRadius: '3px', padding: '2px 6px',
                      cursor: 'pointer', fontSize: '0.65rem', fontFamily: 'inherit'
                    }}
                    title="Switch to Auto mode so web and chat engagement dynamically pause or throttle training"
                  >
                    Switch to Auto
                  </button>
                </span>
              )}

              <span style={{ flex: 1 }} />

              {audioHardwareReady && audioInputs.length > 0 && inputMode !== 'TXT' && (
                <select
                  value={selectedMicId}
                  onChange={e => {
                    const id = e.target.value;
                    setSelectedMicId(id);
                    localStorage.setItem('foveai_mic_device_id', id);
                  }}
                  style={{
                    padding: '4px 8px',
                    background: 'rgba(0,0,0,0.4)',
                    border: '1px solid rgba(255,255,255,0.12)',
                    color: '#fff',
                    borderRadius: '6px',
                    fontFamily: 'Share Tech Mono',
                    fontSize: '0.7rem',
                    maxWidth: '180px',
                    outline: 'none',
                    cursor: 'pointer'
                  }}
                  title="Select Microphone Input (e.g. RODE NT-USB or Webcam Mic to bypass Quest 3 mic silence)"
                >
                  <option value="">🎤 Default Mic</option>
                  {audioInputs.map(d => (
                    <option key={d.deviceId} value={d.deviceId}>
                      🎤 {d.label}
                    </option>
                  ))}
                </select>
              )}

              <button
                disabled={!audioHardwareReady}
                onClick={() => {
                  if (!audioHardwareReady) return;
                  const next = inputMode === 'TXT' ? 'PTT' : inputMode === 'PTT' ? 'VAD' : 'TXT';
                  setInputMode(next);
                  localStorage.setItem('foveai_input_mode', next);
                  if (next !== 'PTT') stopRecording();
                }}
                style={{
                  padding: '5px 12px',
                  fontFamily: 'Share Tech Mono',
                  fontSize: '0.75rem',
                  letterSpacing: '0.08em',
                  borderRadius: '6px',
                  cursor: audioHardwareReady ? 'pointer' : 'not-allowed',
                  opacity: audioHardwareReady ? 1 : 0.4,
                  border: '1px solid',
                  transition: 'all 0.2s',
                  ...(inputMode === 'TXT' ? {
                    color: 'var(--text-muted)',
                    background: 'rgba(255,255,255,0.05)',
                    borderColor: 'rgba(255,255,255,0.12)'
                  } : inputMode === 'PTT' ? {
                    color: '#39ff14',
                    background: 'rgba(57,255,20,0.12)',
                    borderColor: 'rgba(57,255,20,0.4)'
                  } : {
                    color: '#ff6b6b',
                    background: 'rgba(255,107,107,0.15)',
                    borderColor: 'rgba(255,107,107,0.5)'
                  })
                }}
                title={audioHardwareReady ? "Cycle input mode — TXT: text only · PTT: hold ball to talk · VAD: hands-free continuous" : "Audio hardware not found (mic/speaker required for vocal modes)"}
              >
                {inputMode}
              </button>
            </div>

            
            <div className="chat-content-wrapper">


              <div className="chat-messages-container">

              {messages.length === 0 && NEWS.length > 0 && (
                <div style={{ margin: '20px auto', maxWidth: '560px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ fontSize: '0.65rem', letterSpacing: '2px', color: 'var(--accent-cyan)', fontFamily: 'Share Tech Mono', padding: '0 4px' }}>
                    📰 LATEST NEWS
                  </div>
                  {NEWS.slice(0, 3).map((n, i) => (
                    <div
                      key={i}
                      onClick={() => setNewsOverlay(i)}
                      style={{
                        cursor: 'pointer', padding: '10px 14px', borderRadius: '6px',
                        background: 'rgba(0,243,255,0.05)', border: '1px solid rgba(0,243,255,0.25)',
                        fontFamily: 'Share Tech Mono',
                      }}
                    >
                      <div style={{ fontSize: '0.82rem', color: '#fff', fontWeight: 600 }}>{n.title}</div>
                      <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                        {n.date} — click to read
                      </div>
                    </div>
                  ))}
                  <div
                    onClick={() => setActiveTab('News')}
                    style={{ fontSize: '0.65rem', color: 'var(--accent-cyan)', fontFamily: 'Share Tech Mono', cursor: 'pointer', padding: '0 4px' }}
                  >
                    all {NEWS.length} updates →
                  </div>
                </div>
              )}
              {messages.map((msg, idx) => msg.divider ? (
                <div key={idx} className={`session-divider ${classifyByTheme(sessionTitles[msg.divider.sessionId] || msg.divider.title)}`}>
                  <div className="session-divider-line" />
                  {editingSession === msg.divider.sessionId ? (
                    <input
                      className="session-divider-input"
                      value={editTitle}
                      autoFocus
                      onChange={e => setEditTitle(e.target.value)}
                      onBlur={() => commitRename(msg.divider!.sessionId)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') commitRename(msg.divider!.sessionId);
                        if (e.key === 'Escape') setEditingSession(null);
                      }}
                    />
                  ) : (
                    <div
                      className="session-divider-title"
                      title="click to rename this session"
                      onClick={() => { setEditingSession(msg.divider!.sessionId); setEditTitle(sessionTitles[msg.divider!.sessionId] || msg.divider!.title); }}
                    >
                      {sessionTitles[msg.divider.sessionId] || msg.divider.title} ✎
                    </div>
                  )}
                  <div className="session-divider-line" />
                </div>
              ) : (
                <div key={idx} className={`chat-bubble-row ${msg.role}`}>
                  {/* initial-letter avatars dropped (2026-10-08): the name
                      tag inside the bubble says who's who — bubbles got the
                      freed width. First names only. */}
                  {msg.at && (
                    <span className="thread-stamp">
                      {new Date(msg.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  )}
                  <div className={`chat-bubble ${msg.role}`}>
                    <div className="bubble-name">
                      {msg.role === 'user' ? (currentUser?.firstName || 'You') : (currentUser?.aiName?.split(' ')[0] || 'Jen')}
                    </div>
                    {msg.reasoning && <div className="thought-block">{msg.reasoning}</div>}
                    {msg.role === 'assistant' ? renderAssistantContent(msg.content) : displayText(msg.content)}
                  </div>
                </div>
              ))}
              
              {isTyping && (
                <div className="chat-bubble-row ai">
                  <div className="chat-bubble ai">
                  <div className="bubble-name">{currentUser?.aiName?.split(' ')[0] || 'Jen'}</div>
                  </div>
                  <div className="message-content" style={{ padding: '20px 24px' }}>
                    <div className="typing-indicator">
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
            </div>

            <AvatarOverlay show={showAvatar} talking={isTyping} />

            {/* Floating news reader — temporary, closes on backdrop or ✕ */}
            {newsOverlay !== null && NEWS[newsOverlay] && (
              <div
                onClick={() => setNewsOverlay(null)}
                style={{
                  position: 'fixed', inset: 0, zIndex: 1200,
                  background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                <div
                  onClick={e => e.stopPropagation()}
                  style={{
                    width: 'min(640px, 90vw)', maxHeight: '75vh', overflowY: 'auto',
                    background: '#0b0f1a', border: '1px solid rgba(0,243,255,0.35)',
                    borderRadius: '8px', padding: '22px 24px',
                    boxShadow: '0 20px 60px rgba(0,0,0,0.7)',
                    fontFamily: 'Share Tech Mono', position: 'relative',
                  }}
                >
                  <button
                    onClick={() => setNewsOverlay(null)}
                    style={{
                      position: 'absolute', top: '10px', right: '12px',
                      background: 'none', border: 'none', color: 'var(--text-muted)',
                      fontSize: '1.1rem', cursor: 'pointer',
                    }}
                    title="Close"
                  >✕</button>
                  <div style={{ fontSize: '0.62rem', letterSpacing: '2px', color: 'var(--accent-cyan)', marginBottom: '8px' }}>
                    📰 {NEWS[newsOverlay].date} · {NEWS[newsOverlay].tag.toUpperCase()}
                  </div>
                  <div style={{ fontSize: '1rem', color: '#fff', fontWeight: 600, marginBottom: '12px' }}>
                    {NEWS[newsOverlay].title}
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.8)', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                    {NEWS[newsOverlay].detail || NEWS[newsOverlay].body}
                  </div>
                  <div
                    onClick={() => { setNewsOverlay(null); setActiveTab('News'); }}
                    style={{ fontSize: '0.65rem', color: 'var(--accent-cyan)', cursor: 'pointer', marginTop: '16px' }}
                  >
                    see all news →
                  </div>
                </div>
              </div>
            )}

            <div className="chat-input-area">
              <div className="input-wrapper" style={{ display: 'flex', gap: '8px', alignItems: 'center', flex: 1, position: 'relative' }}>
                {isProcessingAudio && (
                  <span style={{ fontFamily: 'Share Tech Mono', fontSize: '0.7rem', color: 'var(--accent-cyan)', whiteSpace: 'nowrap' }}>
                    ⚙️ TRANSCRIBING...
                  </span>
                )}
                
                {/* Peaceful Coexistence: vocal/video mic chip badge + active text input */}
                {inputMode !== 'TXT' && (
                  <div
                    className="vocal-mode-chip"
                    aria-live="polite"
                    style={{
                      flex: '0 0 auto',
                      maxWidth: '220px',
                      padding: '8px 14px',
                      fontSize: '0.8rem',
                      borderRadius: '20px',
                      cursor: 'pointer'
                    }}
                    title={inputMode === 'VAD' ? 'Vocal VAD active (listening). Click or type to send text' : 'Vocal PTT active. Hold ball to talk or type here'}
                  >
                    <span className={`mic-dot ${isRecording ? 'live' : ''}`} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {isRecording ? 'Listening…' : inputMode === 'VAD' ? 'VAD Voice' : 'PTT Voice'}
                    </span>
                  </div>
                )}

                <input 
                  type="text" 
                  className="chat-input"
                  placeholder={
                    pendingMode
                      ? ""
                      : inputMode === 'VAD'
                        ? "Speak anytime or type here to send..."
                        : inputMode === 'PTT'
                          ? "Hold ball to talk or type here..."
                          : getModeExplanation(activeMode)
                  }
                  value={pendingMode ? "" : inputValue}
                  onChange={e => { setInputValue(e.target.value); setPendingMode(null); }}
                  onKeyDown={handleKeyDown}
                  disabled={isTyping || !!pendingMode}
                  style={{ 
                    flex: 1, 
                    transition: 'all 0.3s',
                    borderColor: pendingMode ? 'var(--accent-cyan)' : undefined,
                    boxShadow: pendingMode ? '0 0 15px rgba(0, 243, 255, 0.3) inset' : undefined,
                    background: pendingMode ? 'rgba(0, 243, 255, 0.05)' : undefined
                  }}
                />
                
                {pendingMode && (
                  <div style={{ position: 'absolute', bottom: '75px', right: '10px', pointerEvents: 'none', color: 'var(--accent-cyan)', fontFamily: 'Share Tech Mono', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '10px', background: 'rgba(11, 15, 26, 0.8)', padding: '8px 16px', borderRadius: '12px', border: '1px solid rgba(0, 243, 255, 0.3)', backdropFilter: 'blur(8px)', boxShadow: '0 4px 15px rgba(0,0,0,0.5)', zIndex: 50 }}>
                    <span className="blinking">▶</span>
                    {getModeExplanation(pendingMode)}
                    <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.75rem', marginLeft: '10px' }}>(press ball to lock)</span>
                  </div>
                )}

                <div
                  className={`send-socket ${backendDown ? 'down' : ''} ${!inputValue.trim() || isTyping ? 'idle' : ''} ${isRecording ? 'rec' : ''}`}
                  title={backendDown ? 'backend is down — press to ignite' : 'spin to select mode · press to lock/send'}
                  style={{ zIndex: 100, position: 'relative' }}
                >
                  <SendBall onSend={inputValue.trim() ? backend.state === 'down' ? backend.ignite : handleSendMessage : handleModeConfirm} 
                    health={backend.state === 'up' ? 'ok' : backend.state === 'offline' ? 'off' : backend.state === 'down' ? 'down' : 'warn'}
                    onHoldStart={!backendDown && inputMode === 'PTT' ? startRecording : undefined}
                    onHoldEnd={!backendDown && inputMode === 'PTT' ? stopRecording : undefined}
                    pressHint={backendDown ? 'backend down — press to ignite' : 'press to send · hold to talk'}  onRollStep={handleRollStep} />
                  
                  {(!backendDown || backend.state !== 'starting') && (
                    <div style={{
                      position: 'absolute', inset: 0, 
                      pointerEvents: 'none', 
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '1.6rem',
                      opacity: pendingMode ? 0.9 : 0.4,
                      transition: 'opacity 0.3s, transform 0.3s',
                      transform: pendingMode ? 'scale(1.1)' : 'scale(1)',
                      textShadow: pendingMode ? '0 0 15px rgba(0, 243, 255, 1)' : 'none',
                      zIndex: 10
                    }}
                    key={pendingMode || activeMode} // Forces re-render for potential CSS animations
                    >
                      {(() => {
                        const m = pendingMode || activeMode;
                        return m === 'TEXT' ? '✏️' : 
                               m === 'DICTATE' ? '🗣️' : 
                               m.includes('Vocal') ? '📞' : '🎥';
                      })()}
                    </div>
                  )}

                  {backendDown && (
                    <span className="send-boot">{backend.state === 'starting' ? 'STARTING' : 'STARTUP'}</span>
                  )}
                </div>
              </div>
            </div>
          </>
        )}
      </main>

      {/* Mobile Bottom Navigation Bar */}
      <nav className="bottom-nav">
        <button className={`nav-item ${activeTab === 'Copilot' ? 'active' : ''}`} onClick={() => setActiveTab('Copilot')}>
          <span className="icon">💬</span><span className="label">Copilot</span>
        </button>
        <button className={`nav-item ${activeTab === 'Memory' ? 'active' : ''}`} onClick={() => setActiveTab('Memory')}>
          <span className="icon">🧠</span><span className="label">Memory</span>
        </button>
        <button className={`nav-item ${activeTab === 'News' ? 'active' : ''}`} onClick={() => setActiveTab('News')}>
          <span className="icon">📰</span><span className="label">News</span>
        </button>
        <button className="nav-item menu-toggle-bottom" onClick={() => setSidebarOpen(!sidebarOpen)}>
          <span className="icon">☰</span><span className="label">Menu</span>
        </button>
      </nav>


      <SettingsOverlay isVisible={showSettings} onClose={() => setShowSettings(false)} />
          </div>
  );
}

/* Composer send-ball — the bare trackball seated in a bezel at the right
   end of the input bar. Press = send, press-and-hold = PTT. Rolls for
   the feel of it, but turns no dial (bare mode). */
function SendBall({ onSend, onHoldStart, onHoldEnd, health, pressHint, onRollStep }: { onSend: () => void; onHoldStart?: () => void; onHoldEnd?: () => void; onRollStep?: (dir: number) => void; health?: 'ok' | 'warn' | 'down' | 'off' | null; pressHint?: string }) {
  const tb = useTraits();
  /* 66 of the 75px socket — fills the bezel snugly (was 56: a small dot
     floating in a big room; user: "too small to do anything of use") */
  return <Trackball store={tb} size={74} bare health={health} onPress={onSend} onHoldStart={onHoldStart} onHoldEnd={onHoldEnd} onRollStep={onRollStep} pressHint={pressHint || 'press to send · hold to talk'} />;
}

export default App;
