import os

p = os.path.expanduser("~/FoveAI/Frontend/multigate/src/IgnitionScreen.tsx")
with open(p, "r") as f:
    text = f.read()

# Fix the SNAPSHOT_KEYS list
text = text.replace("{ key: 'XRLF_PROXY_AGGRESSION', label: 'Keep' },", "{ key: 'XRLF_CLOUD_PRESERVE_LAST', label: 'Keep' },")

# Fix the JSX
old_jsx = """                <span className="tk">keep</span>
                <select value={editCompression} onChange={e => { setEditCompression(e.target.value); saveQuick('XRLF_PROXY_AGGRESSION', e.target.value); }}>
                  {['2','4','6','8','16'].map(v => <option key={v} value={v}>{v}</option>)}
                </select>"""

new_jsx = """                <span className="tk">keep</span>
                <select value={editCompression} onChange={e => { setEditCompression(e.target.value); saveQuick('XRLF_CLOUD_PRESERVE_LAST', e.target.value); }}>
                  {['2','4','6','8','16'].map(v => <option key={v} value={v}>{v}</option>)}
                </select>"""

text = text.replace(old_jsx, new_jsx)

# Fix the state loader
old_state = "const comp = rows.find(r => r.key === 'XRLF_PROXY_AGGRESSION')?.current;"
new_state = "const comp = rows.find(r => r.key === 'XRLF_CLOUD_PRESERVE_LAST')?.current;"
text = text.replace(old_state, new_state)

with open(p, "w") as f:
    f.write(text)
