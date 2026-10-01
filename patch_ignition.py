import os

p = os.path.expanduser("~/FoveAI/Frontend/multigate/src/IgnitionScreen.tsx")
with open(p, "r") as f:
    text = f.read()

# Add cadence to snapshot keys
old_keys = """const SNAPSHOT_KEYS: Array<{ key: string; label: string }> = [
  { key: 'XRLF_MODEL_LOCAL_ID', label: 'Local model' },
  { key: 'XRLF_COGNITIVE_MODE', label: 'Cognitive mode' },
  { key: 'XRLF_PROXY_AGGRESSION', label: 'Compression' },
  { key: 'FOVEAI_FRONTEND_UI', label: 'Frontend' },
];"""

new_keys = """const SNAPSHOT_KEYS: Array<{ key: string; label: string }> = [
  { key: 'XRLF_MODEL_LOCAL_ID', label: 'Local model' },
  { key: 'XRLF_COGNITIVE_MODE', label: 'Cognitive mode' },
  { key: 'XRLF_PROXY_AGGRESSION', label: 'Keep' },
  { key: 'FOVEA_COMPRESS_EVERY', label: 'Cadence' },
  { key: 'FOVEAI_FRONTEND_UI', label: 'Frontend' },
];"""

if old_keys in text:
    text = text.replace(old_keys, new_keys)

# Add cadence state
if "const [editCompression" in text:
    text = text.replace("const [editCompression, setEditCompression] = useState('2');", 
                        "const [editCompression, setEditCompression] = useState('2');\n  const [editCadence, setEditCadence] = useState('2');")

if "const comp =" in text:
    text = text.replace("const comp = rows.find(r => r.key === 'XRLF_PROXY_AGGRESSION')?.current;",
                        "const comp = rows.find(r => r.key === 'XRLF_PROXY_AGGRESSION')?.current;\n    const cad = rows.find(r => r.key === 'FOVEA_COMPRESS_EVERY')?.current;\n    if (cad) setEditCadence(cad);")

# Inject slider/select into the JSX
old_jsx = """                <span className="tk">compression</span>
                <select value={editCompression} onChange={e => { setEditCompression(e.target.value); saveQuick('XRLF_PROXY_AGGRESSION', e.target.value); }}>
                  {['1','2','3','4','5'].map(v => <option key={v} value={v}>{v}</option>)}
                </select>"""

new_jsx = """                <span className="tk">keep</span>
                <select value={editCompression} onChange={e => { setEditCompression(e.target.value); saveQuick('XRLF_PROXY_AGGRESSION', e.target.value); }}>
                  {['2','4','6','8','16'].map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                <span className="tk">cadence</span>
                <select value={editCadence} onChange={e => { setEditCadence(e.target.value); saveQuick('FOVEA_COMPRESS_EVERY', e.target.value); }}>
                  {['2','4','8','12','18','24','32'].map(v => <option key={v} value={v}>{v}</option>)}
                </select>"""

if old_jsx in text:
    text = text.replace(old_jsx, new_jsx)

with open(p, "w") as f:
    f.write(text)
