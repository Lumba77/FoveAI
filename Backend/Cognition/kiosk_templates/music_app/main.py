"""Music Toy — WebAudio sequencer pad in a tiny local web app."""

from http.server import BaseHTTPRequestHandler, HTTPServer

PAGE = """<!doctype html><title>Music Toy</title><style>
body{background:#0a0814;color:#e0d0ff;font-family:monospace;margin:20px}
.pad{display:inline-block;width:60px;height:60px;margin:4px;border:1px solid #b080ff;
 border-radius:8px;cursor:pointer;vertical-align:top;text-align:center;line-height:60px}
.pad:active{background:#b080ff}
</style><div id=pads></div>
<script>
const ctx=new (window.AudioContext||window.webkitAudioContext)();
const notes=[261.6,293.7,329.6,392.0,440.0,523.3,587.3,659.3];
const names=['C4','D4','E4','G4','A4','C5','D5','E5'];
const pads=document.getElementById('pads');
notes.forEach((f,i)=>{
 const d=document.createElement('div');d.className='pad';d.textContent=names[i];
 d.onmousedown=()=>{const o=ctx.createOscillator(),g=ctx.createGain();
  o.type='sine';o.frequency.value=f;g.gain.setValueAtTime(.3,ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+1);
  o.connect(g).connect(ctx.destination);o.start();o.stop(ctx.currentTime+1);};
 pads.appendChild(d);});
</script>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(PAGE.encode())

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Music Toy on http://127.0.0.1:8793")
    HTTPServer(("127.0.0.1", 8793), H).serve_forever()
