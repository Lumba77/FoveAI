import sys
with open("/home/lumba/FoveAI/tools/audio-variator-eq/cinnamon-applet/applet.js", "r") as f:
    content = f.read()

old_block = """        // Always render a header row for the theme switcher
        let badgeRow = new St.BoxLayout({ vertical: false, style: "spacing: 6px; margin-bottom: 1px;" });
        if (RACK_LOGO_BADGE || T.wm) {
            try {
                let gicon = new Gio.FileIcon({ file: Gio.File.new_for_path(RACK_DIR + "/foveai-logo.png") });
                badgeRow.add_actor(new St.Icon({ gicon: gicon, icon_size: 18, icon_type: St.IconType.FULLCOLOR }));
            } catch (e) {}
        }
        badgeRow.add_actor(new St.Label({ text: "FOVEAI STUDIO FX", y_align: St.Align.MIDDLE,
            style: `font-size: 8.5px; font-weight: bold; letter-spacing: 2px; color: ${T.acc};` }));

        let spacer = new St.Widget({ x_expand: true });
        badgeRow.add_actor(spacer);"""

new_block = """        // Always render a header row for the theme switcher
        let badgeRow = new St.BoxLayout({ vertical: false, style: "margin-bottom: 8px;" });
        if (RACK_LOGO_BADGE || T.wm) {
            let logoBox = new St.Widget({
                style: `background-image: url("file://${RACK_DIR}/foveai-logo.png"); background-size: contain; background-repeat: no-repeat; width: 140px; height: 27px;`
            });
            badgeRow.add_actor(logoBox);
        }

        let spacer = new St.Widget({ x_expand: true });
        badgeRow.add_actor(spacer);"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/tools/audio-variator-eq/cinnamon-applet/applet.js", "w") as f:
        f.write(content)
    print("Patched successfully")
else:
    print("Could not find block")
