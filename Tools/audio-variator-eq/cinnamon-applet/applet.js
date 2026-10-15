const Applet = imports.ui.applet;
const Lang = imports.lang;
const Mainloop = imports.mainloop;
const Gio = imports.gi.Gio;
const Interfaces = imports.misc.interfaces;
const Util = imports.misc.util;
const Cinnamon = imports.gi.Cinnamon;
const Clutter = imports.gi.Clutter;
const St = imports.gi.St;
const PopupMenu = imports.ui.popupMenu;
const GLib = imports.gi.GLib;
const Cvc = imports.gi.Cvc;
const Tooltips = imports.ui.tooltips;
const Main = imports.ui.main;
const Settings = imports.ui.settings;
const Slider = imports.ui.slider;
const Pango = imports.gi.Pango;

const MEDIA_PLAYER_2_PATH = "/org/mpris/MediaPlayer2";
const MEDIA_PLAYER_2_NAME = "org.mpris.MediaPlayer2";
const MEDIA_PLAYER_2_PLAYER_NAME = "org.mpris.MediaPlayer2.Player";

// how long to show the output icon when volume is adjusted during media playback.
const OUTPUT_ICON_SHOW_TIME_SECONDS = 3;

/* global values */
let players_without_seek_support = ['telegram desktop', 'spotify', 'totem', 'xplayer', 'gnome-mplayer', 'pithos',
    'smplayer'];
let players_with_seek_support = [
    'clementine', 'banshee', 'rhythmbox', 'rhythmbox3', 'pragha', 'quodlibet',
    'amarok', 'xnoise', 'gmusicbrowser', 'vlc', 'qmmp', 'deadbeef', 'audacious'];
/* dummy vars for translation */
let x = _("Playing");
x = _("Paused");
x = _("Stopped");

const VOLUME_ADJUSTMENT_STEP = 0.05; /* Volume adjustment step in % */

const ICON_SIZE = 28;

const CINNAMON_DESKTOP_SOUNDS = "org.cinnamon.desktop.sound";
const OVERAMPLIFICATION_KEY = "allow-amplified-volume";

/* ── FX-rack LCD themes ────────────────────────────────────────────────
 * Palette for the rack units and LCD screens under the volume/mic
 * sliders. Selected via applet settings ("FX Rack ▸ Theme"):
 *   phosphor    — the original green-LCD look (as it is now)
 *   glass-dark  — jenna-vscode glass LCD: near-black glass plate,
 *                 teal glowing values, slate labels
 *   glass-light — frosted light variant of the same
 *   onyx-logo   — black faceplate, amber accents, FoveAI logo watermark
 *                 behind the rack (and optional badge in the header)
 */
const RACK_THEMES = {
    "phosphor": {
        tex: "phosphor",
        cardBg: "rgba(13,26,16,0.80)", cardBd: "#1e3a26", btnBg: "rgba(20,38,26,0.85)", ddBg: "rgba(10,20,13,0.90)",
        val: "#7dff9e", valGlow: "rgba(125,255,158,0.6)",
        acc: "#ffb64d", accDim: "#d19a4d", dim: "#4d8f5f", dim2: "#3a6b48",
        head: "#888888", hint: "#555555", div: "#444444", utilBd: "#444444",
        inset: "inset 0 1px 4px rgba(0,0,0,0.7)", eqBar: "#7dff9e",
        wm: false,
        mc: { neutral: "#888888", low: "#ff9933", mid: "#4da6ff", high: "#33ccff" }
    },
    "glass-dark": {
        tex: "glass-dark",
        cardBg: "rgba(14,17,24,0.55)", cardBd: "rgba(255,255,255,0.10)", btnBg: "rgba(255,255,255,0.06)", ddBg: "rgba(7,8,10,0.80)",
        val: "#5eead4", valGlow: "rgba(94,234,212,0.55)",
        acc: "#e5b563", accDim: "#b08d4d", dim: "#64748b", dim2: "#475569",
        head: "#cbd5e1", hint: "#64748b", div: "rgba(255,255,255,0.12)", utilBd: "rgba(255,255,255,0.16)",
        inset: "inset 0 1px 4px rgba(0,0,0,0.6)", eqBar: "#5eead4",
        wm: false,
        mc: { neutral: "#94a3b8", low: "#f5b04d", mid: "#5eead4", high: "#38bdf8" }
    },
    "glass-light": {
        tex: "glass-light",
        cardBg: "rgba(255,255,255,0.55)", cardBd: "rgba(15,23,42,0.16)", btnBg: "rgba(255,255,255,0.45)", ddBg: "rgba(230,235,242,0.80)",
        val: "#0d7a70", valGlow: "rgba(13,148,136,0.35)",
        acc: "#b45309", accDim: "#92702f", dim: "#64748b", dim2: "#94a3b8",
        head: "#334155", hint: "#94a3b8", div: "rgba(15,23,42,0.15)", utilBd: "rgba(15,23,42,0.20)",
        inset: "inset 0 1px 3px rgba(15,23,42,0.14)", eqBar: "#0d7a70",
        wm: false,
        mc: { neutral: "#64748b", low: "#d97706", mid: "#0d7a70", high: "#0284c7" }
    },
    "onyx-logo": {
        tex: "onyx-logo",
        cardBg: "rgba(8,8,10,0.75)", cardBd: "rgba(251,191,36,0.30)", btnBg: "rgba(30,27,20,0.85)", ddBg: "rgba(4,4,4,0.90)",
        val: "#f4f4f5", valGlow: "rgba(244,244,245,0.45)",
        acc: "#fbbf24", accDim: "#c8942e", dim: "#9ca3af", dim2: "#6b7280",
        head: "#e4e4e7", hint: "#71717a", div: "#3f3f46", utilBd: "#52525b",
        inset: "inset 0 1px 4px rgba(0,0,0,0.85)", eqBar: "#fbbf24",
        wm: true,
        mc: { neutral: "#a1a1aa", low: "#f59e0b", mid: "#e5e7eb", high: "#fbbf24" }
    }
};

let RACK_DIR = GLib.get_home_dir() + "/.local/share/cinnamon/applets/sound@cinnamon.org";
let RACK_LOGO_BADGE = true;
let RACK_WM = "";
let T = RACK_THEMES["phosphor"];
// composite skin fragments, rebuilt by _applyRackTheme
let RACK_PANEL = "", RACK_DEEP = "", RACK_BTN = "";

function _rackImg(name) {
    return "file://" + RACK_DIR + "/" + name;
}

// small glowing LED pip — sits inside buttons / beside module titles
function _ledDot(color, size) {
    size = size || 6;
    return new St.Widget({
        style: "width: " + size + "px; height: " + size + "px; border-radius: " + (size / 2) + "px; " +
               "background-color: " + color + "; box-shadow: 0 0 " + size + "px " + color + ";",
        y_align: St.Align.MIDDLE
    });
}

function _applyRackTheme(key) {
    T = RACK_THEMES[key] || RACK_THEMES["phosphor"];
    let tex = T.tex;
    // 9-sliced glass textures removed since images are missing
    RACK_PANEL = "background-color: " + T.cardBg + "; border: 1px solid " + T.cardBd + "; border-radius: 10px; box-shadow: " + T.inset + ";";
    RACK_DEEP  = "background-color: " + T.ddBg + "; border: 1px solid " + T.cardBd + "; border-radius: 10px; box-shadow: " + T.inset + ";";
    RACK_BTN   = "background-color: " + T.btnBg + "; border: 1px solid " + T.cardBd + "; border-radius: 6px;";
    RACK_WM = T.wm
        ? "background-image: url(\"" + _rackImg("foveai-logo-bg.png") + "\"); background-repeat: no-repeat; background-position: top center; background-size: auto 95%;"
        : "";
}
_applyRackTheme("phosphor");

class ControlButton {
    constructor(icon, tooltip, callback, small = false) {
        this.actor = new St.Bin();

        this.button = new St.Button();
        this.button.connect('clicked', callback);

        if(small)
            this.button.add_style_pseudo_class("small");

        this.icon = new St.Icon({
            icon_type: St.IconType.SYMBOLIC,
            icon_name: icon
        });
        this.button.set_child(this.icon);
        this.actor.add_actor(this.button);

        this.tooltip = new Tooltips.Tooltip(this.button, tooltip);
    }

    getActor() {
        return this.actor;
    }

    setData(icon, tooltip) {
        this.icon.icon_name = icon;
        this.tooltip.set_text(tooltip);
    }

    setActive(status) {
        this.button.change_style_pseudo_class("active", status);
    }

    setEnabled(status) {
        this.button.change_style_pseudo_class("insensitive", !status);
        this.button.can_focus = status;
        this.button.reactive = status;
    }
}

class VolumeSlider extends PopupMenu.PopupSliderMenuItem {
    constructor(applet, stream, tooltip, app_icon) {
        super(0);
        this.applet = applet;

        if(tooltip)
            this.tooltipText = tooltip + ": ";
        else
            this.tooltipText = "";

        this.tooltip = new Tooltips.Tooltip(this.actor, this.tooltipText);

        this.connect("value-changed", () => this._onValueChanged());
        if (tooltip === _("Volume")) {
            this.connect("drag-end", () => this._onDragEnd());
        }

        this.app_icon = app_icon;
        if (this.app_icon == null) {
            this.iconName = this.isMic ? "xsi-microphone-sensitivity-muted" : "xsi-audio-volume-muted";
            this.icon = new St.Icon({icon_name: this.iconName, icon_type: St.IconType.SYMBOLIC, icon_size: 16});
        }
        else {
            this.icon = new St.Icon({icon_name: this.app_icon, icon_type: St.IconType.FULLCOLOR, icon_size: 16});
        }

        this.icon.reactive = true;
        this.icon.track_hover = true;
        this.icon.connect('button-press-event', (actor, event) => {
            if (this.stream && event.get_button() === 1) {
                this.stream.change_is_muted(!this.stream.is_muted);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });

        this.removeActor(this._slider);
        this.addActor(this.icon, {span: 0});
        this.addActor(this._slider, {span: -1, expand: true});

        this.connectWithStream(stream);
    }

    connectWithStream(stream) {
        if (!stream) {
            this.actor.hide();
            this.stream = null;
        } else {
            this.actor.show();
            this.stream = stream;
            this.isMic = stream instanceof Cvc.MixerSource || stream instanceof Cvc.MixerSourceOutput;
            this.isOutputSink = stream instanceof Cvc.MixerSink;

            let mutedId = stream.connect("notify::is-muted", () => this._update());
            let volumeId = stream.connect("notify::volume", () => this._update());
            this.connect("destroy", () => {
                stream.disconnect(mutedId);
                stream.disconnect(volumeId);
            });
        }

        this._update();
    }

    _onValueChanged() {
        if (!this.stream) return;

        let muted;
        // Use the scaled volume max only for the main output
        let volume = this._value * this.applet._volumeMax;

        if(this._value < 0.005) {
            volume = 0;
            muted = true;
        } else {
            muted = false;
            //100% is magnetic:
            if (volume != this.applet._volumeNorm && volume > this.applet._volumeNorm*(1-VOLUME_ADJUSTMENT_STEP/2) && volume < this.applet._volumeNorm*(1+VOLUME_ADJUSTMENT_STEP/2))
                volume = this.applet._volumeNorm;
        }
        this.stream.volume = volume;
        this.stream.push_volume();

        if(this.stream.is_muted !== muted)
            this.stream.change_is_muted(muted);

        if(!this._dragging)
            this.applet._notifyVolumeChange(this.stream);
    }

    _onDragEnd() {
        if (this.stream) {
            this.applet._notifyVolumeChange(this.stream);
        }
    }

    _onScrollEvent(actor, event) {
        let direction = event.get_scroll_direction();

        if (direction == Clutter.ScrollDirection.DOWN) {
            this._value = Math.max(0, this._value - VOLUME_ADJUSTMENT_STEP/this.applet._volumeMax*this.applet._volumeNorm);
        }
        else if (direction == Clutter.ScrollDirection.UP) {
            this._value = Math.min(1, this._value + VOLUME_ADJUSTMENT_STEP/this.applet._volumeMax*this.applet._volumeNorm);
        }

        this._slider.queue_repaint();
        this.tooltip.show();
        this.emit('value-changed', this._value);
    }

    _onKeyPressEvent(actor, event) {
        const key = event.get_key_symbol();
        if (key === Clutter.KEY_Right || key === Clutter.KEY_Left) {
            let delta = key === Clutter.KEY_Right ? VOLUME_ADJUSTMENT_STEP : -VOLUME_ADJUSTMENT_STEP;
            if (St.Widget.get_default_direction() === St.TextDirection.RTL)
                delta = -delta;

            this._value = Math.max(0, Math.min(this._value + delta/this.applet._volumeMax*this.applet._volumeNorm, 1));
            this._slider.queue_repaint();
            this.emit('value-changed', this._value);
            return true;
        }
        return false;
    }


    _update() {
        // value: percentage of volume_max (set as value in the widget)
        // visible_value: percentage of volume_norm (shown to the user)
        // these only differ for the output, and only when the user changes the maximum volume
        let volume = (!this.stream || this.stream.is_muted) ? 0 : this.stream.volume;
        let value, visible_value, delta = VOLUME_ADJUSTMENT_STEP * this.applet._volumeMax / this.applet._volumeNorm;

        if (this.isOutputSink) {
            value = volume / this.applet._volumeMax;
            visible_value = volume / this.applet._volumeNorm;
            if (visible_value != 1 && visible_value > 1 - delta/2 && visible_value < 1 + delta/2) {
                visible_value = 1; // 100% is magnetic
                value = this.applet._volumeNorm / this.applet._volumeMax;
                this.applet._output.volume = this.applet._volumeNorm;
                this.applet._output.push_volume();
            }
        } else {
            value = volume / this.applet._volumeMax;
            visible_value = volume / this.applet._volumeNorm;
        }

        let percentage = Math.round(visible_value * 100) + "%";

        this.tooltip.set_text(this.tooltipText + percentage);
        if (this._dragging)
            this.tooltip.show();
        let iconName = this._volumeToIcon(value);
        if (this.app_icon == null) {
            this.icon.icon_name = iconName;
        }
        this.setValue(value);

        // send data to applet
        this.emit("values-changed", iconName, percentage);
    }

    _volumeToIcon(value) {
        let icon;
        if(value < 0.005) {
            icon = "muted";
        } else {
            let n = Math.floor(3 * value);
            if(n < 1)
                icon = "low";
            else if(n < 2)
                icon = "medium";
            else
                icon = "high";
        }
        return this.isMic? "xsi-microphone-sensitivity-" + icon : "xsi-audio-volume-" + icon;
    }
}

class ScrewKnob {
    constructor(name, subtitle, tooltipText, minVal, maxVal, step, unit, initialVal, onChange) {
        this.name = name;
        this.subtitle = subtitle;
        this.minVal = minVal;
        this.maxVal = maxVal;
        this.step = step;
        this.unit = unit;
        this.value = initialVal;
        this.onChange = onChange;

        this.actor = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style: `spacing: 1px; padding: 5px 6px; border-radius: 6px; ${RACK_PANEL}`
        });

        let lblName = new St.Label({
            text: this.name,
            style: `font-size: 10.5px; font-weight: bold; color: ${T.acc}; text-align: center; letter-spacing: 1px;`
        });
        this.actor.add_actor(lblName);

        this.lblVal = new St.Label({
            text: this.formatValue(),
            style: `font-size: 17px; font-weight: bold; font-family: monospace; color: ${T.val}; text-align: center; text-shadow: 0 0 6px ${T.valGlow};`
        });
        this.actor.add_actor(this.lblVal);

        let lblSub = new St.Label({
            text: this.subtitle + "  [" + this._rangeText() + "]",
            style: `font-size: 8.5px; font-family: monospace; color: ${T.dim}; text-align: center;`
        });
        this.actor.add_actor(lblSub);

        let row = new St.BoxLayout({ vertical: false, style: "spacing: 4px; margin-top: 3px;" });

        let btnMinus = new St.Button({
            label: "−",
            x_expand: true,
            style: `font-size: 13px; padding: 2px 6px; border-radius: 4px; color: ${T.val}; ${RACK_BTN}`
        });
        btnMinus.connect('clicked', () => this.adjust(-this.step));

        let btnPlus = new St.Button({
            label: "+",
            x_expand: true,
            style: `font-size: 13px; padding: 2px 6px; border-radius: 4px; color: ${T.val}; ${RACK_BTN}`
        });
        btnPlus.connect('clicked', () => this.adjust(this.step));

        row.add_actor(btnMinus);
        row.add_actor(btnPlus);
        this.actor.add_actor(row);

        this.tooltip = new Tooltips.Tooltip(this.actor, tooltipText);

        this.actor.reactive = true;
        this.actor.connect('scroll-event', (actor, event) => {
            let direction = event.get_scroll_direction();
            if (direction === Clutter.ScrollDirection.UP) {
                this.adjust(this.step);
            } else if (direction === Clutter.ScrollDirection.DOWN) {
                this.adjust(-this.step);
            }
            return Clutter.EVENT_STOP;
        });
    }

    formatValue() {
        let prefix = this.value > 0 ? "+" : "";
        return prefix + this.value.toFixed(1) + this.unit;
    }

    _rangeText() {
        return this.minVal + ".." + this.maxVal + this.unit;
    }

    adjust(delta) {
        this.setValue(Math.min(this.maxVal, Math.max(this.minVal, this.value + delta)));
        if (this.onChange) {
            this.onChange(this.value);
        }
    }

    setValue(newVal) {
        this.value = Math.round(newVal * 2) / 2;
        this.lblVal.set_text(this.formatValue());
    }
}

class FreqBalButton {
    constructor(title, subtitle, modes, initialMode, onChange) {
        this.title = title;
        this.subtitle = subtitle;
        this.modes = modes;
        this.mode = initialMode || "neutral";
        this.onChange = onChange;

        this.labels = {
            "neutral": "[ = ] FLAT",
            "low":     "[ ◄ ] LOW",
            "mid":     "[ ● ] MID",
            "high":    "[ ► ] HIGH"
        };
        this.colors = {
            "neutral": T.mc.neutral,
            "low":     T.mc.low,
            "mid":     T.mc.mid,
            "high":    T.mc.high
        };

        this.actor = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style: `spacing: 2px; padding: 5px 5px; min-width: 58px; border-radius: 6px; ${RACK_PANEL}`
        });

        let lblTitle = new St.Label({
            text: this.title,
            style: `font-size: 10.5px; font-weight: bold; color: ${T.acc}; text-align: center; letter-spacing: 1px;`
        });
        this.actor.add_actor(lblTitle);

        let lblSub = new St.Label({
            text: this.subtitle,
            style: `font-size: 8.5px; font-family: monospace; color: ${T.dim}; text-align: center; margin-bottom: 3px;`
        });
        this.actor.add_actor(lblSub);

        this.button = new St.Button({
            label: this.labels[this.mode] || "[ = ] FLAT",
            style: this.getStyle()
        });
        this.button.connect('clicked', () => this.cycle());
        this.actor.add_actor(this.button);

        this.tooltip = new Tooltips.Tooltip(this.actor, "Freq. Bal: Emphasizes the high or low frequency ranges");
    }

    getStyle() {
        let col = this.colors[this.mode] || T.mc.neutral;
        return "font-size: 11px; font-family: monospace; font-weight: bold; color: " + col + "; border: 1px solid " + T.cardBd + "; border-radius: 4px; padding: 4px 3px; background-color: " + T.btnBg + ";";
    }

    cycle() {
        let idx = (this.modes.indexOf(this.mode) + 1) % this.modes.length;
        this.setMode(this.modes[idx]);
        if (this.onChange) {
            this.onChange(this.mode);
        }
    }

    setMode(newMode) {
        this.mode = newMode;
        this.button.set_label(this.labels[this.mode] || "[ = ] FLAT");
        this.button.set_style(this.getStyle());
    }
}

class EqualizerRackSection extends PopupMenu.PopupBaseMenuItem {
    constructor() {
        super({ activate: false, hover: false });

        let container = new St.BoxLayout({
            vertical: true,
            style: "spacing: 2px; padding: 2px 2px; margin: 1px 0px;"
        });

        // Board surface header
        let headerRow = new St.BoxLayout({ vertical: false, style: "spacing: 6px; margin-bottom: 2px;" });
        let lblHeader = new St.Label({
            text: "🎛 3-BAND HARMONIC EQUALIZER",
            style: `font-size: 8.5px; font-weight: bold; color: ${T.head};`
        });
        let lblHint = new St.Label({
            text: "• Scroll or click +/−",
            style: `font-size: 7.5px; color: ${T.hint}; font-style: italic;`
        });
        headerRow.add_actor(lblHeader);
        headerRow.add_actor(lblHint);
        container.add_actor(headerRow);

        let screwsRow = new St.BoxLayout({
            vertical: false,
            style: "spacing: 3px;"
        });

        let state = { bass: 0.0, mid: 0.0, treble: 0.0, bal_low: "neutral", bal_high: "neutral", pitch: 0, warp: 0 };
        try {
            let [res, stdout] = GLib.spawn_command_line_sync("/home/lumba/.local/bin/set-eq --json");
            if (res) {
                let parsed = JSON.parse(new TextDecoder().decode(stdout));
                state = Object.assign(state, parsed);
            }
        } catch (e) {
            global.logError("Failed to load initial EQ state: " + e);
        }

        // BASS Knob
        this.knobBass = new ScrewKnob("BASS", "Sub & Kick", "Bass (100 Hz): Low-end depth and punch", -12.0, 12.0, 1.0, "dB", state.bass, (v) => {
            Util.spawnCommandLine("/home/lumba/.local/bin/set-eq --bass " + v.toFixed(1));
        });

        // Freq. Bal Low (between Bass and Mid)
        this.balLow = new FreqBalButton("Freq. Bal.", "Low / Mid", ["neutral", "low", "mid"], state.bal_low, (mode) => {
            Util.spawnCommandLine("/home/lumba/.local/bin/set-eq --bal-low " + mode);
        });

        // MID Knob
        this.knobMid = new ScrewKnob("MID", "Vocals", "Mids (1 kHz): Vocal clarity and body", -12.0, 12.0, 1.0, "dB", state.mid, (v) => {
            Util.spawnCommandLine("/home/lumba/.local/bin/set-eq --mid " + v.toFixed(1));
        });

        // Freq. Bal High (between Mid and Treble)
        this.balHigh = new FreqBalButton("Freq. Bal.", "Mid / High", ["neutral", "mid", "high"], state.bal_high, (mode) => {
            Util.spawnCommandLine("/home/lumba/.local/bin/set-eq --bal-high " + mode);
        });

        // TREBLE Knob
        this.knobTreb = new ScrewKnob("TREBLE", "Air / Detail", "Treble (8 kHz): Brightness, cymbals, air", -12.0, 12.0, 1.0, "dB", state.treble, (v) => {
            Util.spawnCommandLine("/home/lumba/.local/bin/set-eq --treble " + v.toFixed(1));
        });

        screwsRow.add_actor(this.knobBass.actor);
        screwsRow.add_actor(this.balLow.actor);
        screwsRow.add_actor(this.knobMid.actor);
        screwsRow.add_actor(this.balHigh.actor);
        screwsRow.add_actor(this.knobTreb.actor);

        container.add_actor(screwsRow);

        // --- Pitch & Tape Glide Section ---
        let pitchHeaderRow = new St.BoxLayout({ vertical: false, style: "spacing: 6px; margin-top: 4px; margin-bottom: 1px;" });
        let lblPitchHeader = new St.Label({
            text: "🎵 PITCH & TAPE GLIDE",
            style: `font-size: 8.5px; font-weight: bold; color: ${T.head};`
        });
        pitchHeaderRow.add_actor(lblPitchHeader);
        container.add_actor(pitchHeaderRow);

        let pitchRow = new St.BoxLayout({
            vertical: false,
            style: "spacing: 5px;"
        });

        this.knobPitch = new ScrewKnob("PITCH", "Tone / Key", "Pitch Shift: Changes musical key without changing speed", -12.0, 12.0, 1.0, "st", state.pitch || 0, (v) => {
            Util.spawnCommandLine("/home/lumba/.local/bin/set-eq --pitch " + Math.round(v));
        });

        this.knobWarp = new ScrewKnob("WARP", "Tape Glide", "Warp: Analog tape / turntable pitch glide in cents", -100.0, 100.0, 10.0, "ct", state.warp || 0, (v) => {
            Util.spawnCommandLine("/home/lumba/.local/bin/set-eq --warp " + v.toFixed(1));
        });

        let btnZeroPitch = new St.Button({
            label: "0 RESET",
            style: `font-size: 8px; font-weight: bold; color: ${T.head}; border: 1px solid ${T.utilBd}; border-radius: 4px; padding: 2px 5px; margin-top: 8px;`
        });
        btnZeroPitch.connect('clicked', () => {
            this.knobPitch.setValue(0);
            this.knobWarp.setValue(0);
            Util.spawnCommandLine("/home/lumba/.local/bin/set-eq --pitch 0 --warp 0");
        });

        pitchRow.add_actor(this.knobPitch.actor);
        pitchRow.add_actor(this.knobWarp.actor);
        pitchRow.add_actor(btnZeroPitch);
        container.add_actor(pitchRow);

        this.addActor(container, { expand: true, span: -1 });
    }
}

// ---- LCD parameter: numeric or choice list ----
class LcdParam {
    constructor(name, min, max, step, unit, value, choices) {
        this.name = name;
        this.min = min; this.max = max; this.step = step; this.unit = unit;
        this.value = value;
        this.choices = choices || null;
        this.onAdj = null;   // set by owner: fired after value changes
    }

    disp() {
        if (this.fmt)
            return this.fmt(this.value);
        if (this.choices)
            return String(this.value).toUpperCase();
        return (this.value > 0 ? "+" : "") + this.value.toFixed(1) + this.unit;
    }

    setTo(v) {
        this.setVal(v);
        if (this.onAdj) this.onAdj(this.value);
    }

    rangeText() {
        if (this.choices) {
            let s = this.choices.join("/");
            return s.length > 38 ? this.choices.length + " options" : s;
        }
        return this.min + ".." + this.max + this.unit;
    }

    adj(dir) {
        if (this.choices) {
            let i = this.choices.indexOf(this.value);
            this.value = this.choices[(i + dir + this.choices.length) % this.choices.length];
        } else {
            this.value = Math.min(this.max, Math.max(this.min, this.value + dir * this.step));
        }
        if (this.onAdj) this.onAdj(this.value);
    }

    setVal(v) {
        this.value = this.choices ? v : Math.min(this.max, Math.max(this.min, v));
    }
}

// ---- RBJ biquad magnitude response (dB) for the EQ curve display ----
function _eqBandDb(kind, f0, q, gainDb, f) {
    let sr = 48000;
    let A = Math.pow(10, gainDb / 40);
    let w0 = 2 * Math.PI * f0 / sr, cw = Math.cos(w0), sw = Math.sin(w0);
    let alpha = sw / (2 * q);
    let b0, b1, b2, a0, a1, a2;
    if (kind === "peak") {
        b0 = 1 + alpha * A; b1 = -2 * cw; b2 = 1 - alpha * A;
        a0 = 1 + alpha / A; a1 = -2 * cw; a2 = 1 - alpha / A;
    } else {
        let sq = 2 * Math.sqrt(A) * alpha;
        if (kind === "low") {
            b0 = A * ((A + 1) - (A - 1) * cw + sq); b1 = 2 * A * ((A - 1) - (A + 1) * cw); b2 = A * ((A + 1) - (A - 1) * cw - sq);
            a0 = (A + 1) + (A - 1) * cw + sq;       a1 = -2 * ((A - 1) + (A + 1) * cw);     a2 = (A + 1) + (A - 1) * cw - sq;
        } else {
            b0 = A * ((A + 1) + (A - 1) * cw + sq); b1 = -2 * A * ((A - 1) + (A + 1) * cw); b2 = A * ((A + 1) + (A - 1) * cw - sq);
            a0 = (A + 1) - (A - 1) * cw + sq;       a1 = 2 * ((A - 1) - (A + 1) * cw);      a2 = (A + 1) - (A - 1) * cw - sq;
        }
    }
    let w = 2 * Math.PI * f / sr, c1 = Math.cos(w), c2 = Math.cos(2 * w);
    let num = b0 * b0 + b1 * b1 + b2 * b2 + 2 * (b0 * b1 + b1 * b2) * c1 + 2 * b0 * b2 * c2;
    let den = a0 * a0 + a1 * a1 + a2 * a2 + 2 * (a0 * a1 + a1 * a2) * c1 + 2 * a0 * a2 * c2;
    return 10 * Math.log10(Math.max(num / den, 1e-10));
}

// ---- LCD module: compact face (sub / value / label rows), click opens detail ----
class LcdModule {
    // params: all adjustable params (shown as rows in the detail view)
    // cells:  face layout — [{ main: LcdParam, sub: LcdParam|null }]; default = one cell per param
    constructor(title, params, section, cells) {
        this.title = title;
        this.params = params;
        this.section = section;
        this.cells = cells || params.map(p => ({ main: p, sub: null }));
        this._faces = [];

        this.actor = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style: `spacing: 0px; padding: 4px 5px 3px 5px; border-radius: 6px; ${RACK_PANEL}`
        });
        let titleRow = new St.BoxLayout({ style: "spacing: 4px;", x_expand: true, x_align: Clutter.ActorAlign.CENTER });
        titleRow.add_actor(_ledDot(T.acc, 4));
        titleRow.add_actor(new St.Label({
            text: title,
            style: `font-size: 9px; font-weight: bold; color: ${T.acc}; letter-spacing: 1px; text-align: center; margin-bottom: 1px; text-shadow: 0 0 5px ${T.accDim};`
        }));
        this.actor.add_actor(titleRow);

        let cellsRow = new St.BoxLayout({ style: "spacing: 2px;" });
        for (let c of this.cells) {
            let cell = new St.BoxLayout({ vertical: true, x_expand: true });
            let face = { main: c.main, sub: c.sub };
            let lsub = new St.Label({
                text: "",
                style: `font-size: 8px; font-family: monospace; color: ${T.accDim}; text-align: center; min-height: 10px;`
            });
            face.subLabel = lsub;
            if (c.sub) {
                lsub.reactive = true;
                lsub.connect('scroll-event', (a, e) => {
                    let d = e.get_scroll_direction();
                    if (d === Clutter.ScrollDirection.UP) c.sub.adj(1);
                    else if (d === Clutter.ScrollDirection.DOWN) c.sub.adj(-1);
                    return Clutter.EVENT_STOP;
                });
            }
            cell.add_actor(lsub);

            let lv = new St.Label({
                text: "",
                style: `font-size: 12px; font-family: monospace; font-weight: bold; color: ${T.val}; text-shadow: 0 0 5px ${T.valGlow}; text-align: center;`
            });
            face.valLabel = lv;
            cell.add_actor(lv);
            cell.add_actor(new St.Label({
                text: c.main.name,
                style: `font-size: 7.5px; font-family: monospace; color: ${T.dim}; text-align: center;`
            }));
            cell.reactive = true;
            cell.connect('scroll-event', (a, e) => {
                let d = e.get_scroll_direction();
                if (d === Clutter.ScrollDirection.UP) c.main.adj(1);
                else if (d === Clutter.ScrollDirection.DOWN) c.main.adj(-1);
                return Clutter.EVENT_STOP;
            });
            new Tooltips.Tooltip(cell, c.main.tip || c.main.name);
            this._faces.push(face);
            cellsRow.add_actor(cell);
        }
        this.actor.add_actor(cellsRow);

        this.actor.reactive = true;
        this.actor.connect('button-press-event', () => {
            this.section.toggleDetail(this);
            return Clutter.EVENT_STOP;
        });
        this.refresh();
    }

    refresh() {
        for (let f of this._faces) {
            f.valLabel.set_text(f.main.disp());
            f.subLabel.set_text(f.sub ? f.sub.disp() : "");
        }
    }
}

class StudioMixerSection extends PopupMenu.PopupBaseMenuItem {
    constructor(outVolItem, inVolItem, applet) {
        super({ activate: false, hover: false });
        this._openModule = null;
        this._detailRows = [];
        this._modules = [];
        this.applet = applet;

        let container = new St.BoxLayout({
            vertical: true,
            style: `spacing: 6px; padding: 4px 6px; margin: 1px 0px; min-width: 420px; ${RACK_WM}`
        });
        container.set_clip_to_allocation(true);

        // Always render a header row for the theme switcher
        let badgeRow = new St.BoxLayout({ vertical: false, style: "margin-bottom: 8px;" });
        if (RACK_LOGO_BADGE || T.wm) {
            let logoBox = new St.Widget({
                style: `background-image: url("file://${RACK_DIR}/foveai-logo.png"); background-size: contain; background-repeat: no-repeat; width: 140px; height: 27px;`
            });
            badgeRow.add_actor(logoBox);
        }

        let spacer = new St.Widget({ x_expand: true });
        badgeRow.add_actor(spacer);

        container.add_actor(badgeRow);

        let colsRow = new St.BoxLayout({ vertical: false, style: "spacing: 10px;" });

        // ================= LEFT: OUTPUT =================
        let leftCol = new St.BoxLayout({ vertical: true, x_expand: true, style: "spacing: 4px;" });
        leftCol.add_actor(new St.Label({ text: "🔊 OUTPUT", style: `font-size: 8.5px; font-weight: bold; color: ${T.head};` }));
        leftCol.add_actor(outVolItem.actor);

        let state = { bass: 0.0, mid: 0.0, treble: 0.0, bal_low: "neutral", bal_high: "neutral", pitch: 0, warp: 0,
                      compressor: 0, loudness: 0, chorus: 0, reverb: 0, modulator: 0, width: 0 };
        try {
            let [res, stdout] = GLib.spawn_command_line_sync("/home/lumba/.local/bin/set-eq --json");
            if (res) state = Object.assign(state, JSON.parse(new TextDecoder().decode(stdout)));
        } catch (e) {}

        const EQC = "/home/lumba/.local/bin/set-eq";
        const MXC = "/home/lumba/.local/bin/set-mic-fx";
        this._allParams = [];
        this._presets = { scenes: {}, units: {}, cats: {} };
        try {
            let [pr, pout] = GLib.spawn_command_line_sync(EQC + " --presets-json");
            if (pr) this._presets = Object.assign(this._presets, JSON.parse(new TextDecoder().decode(pout)));
        } catch (e) {}

        const mkp = (name, min, max, step, unit, val, choices, mkCmd, tip, key) => {
            let p = new LcdParam(name, min, max, step, unit, val, choices);
            p.tip = tip;
            let spawning = false, queued = null;
            p.onAdj = (v) => {
                this._refreshAll();
                if (spawning) { queued = v; return; }
                spawning = true;
                Util.spawnCommandLine(mkCmd(v));
                Mainloop.timeout_add(70, () => {
                    spawning = false;
                    if (queued !== null) { let q = queued; queued = null; p.onAdj(q); }
                    return false;
                });
            };
            p.stateKey = key;
            this._allParams.push(p);
            return p;
        };
        const eqp = (n,mi,ma,st,u,v,k,t) => mkp(n,mi,ma,st,u,v,null,(x)=>EQC+" "+k+" "+x.toFixed(1),t,k.replace(/^--/,'').replace(/-/g,'_'));
        const fxp = (n,v,k,t) => mkp(n,0,100,5,"%",v,null,(x)=>MXC+" "+k+" "+Math.round(x),t);
        const pair = (m1, m2, col) => {
            let r = new St.BoxLayout({style:"spacing: 5px;"});
            r.add_actor(m1.actor); if (m2) r.add_actor(m2.actor);
            col.add_actor(r);
            this._modules.push(m1); if (m2) this._modules.push(m2);
        };

        // ---- OUTPUT modules ----
        let pBass  = eqp("BAS",-12,12,1,"dB",state.bass,"--bass","Bass (100 Hz): low-end depth and punch");
        let pMid   = eqp("MID",-12,12,1,"dB",state.mid,"--mid","Mids (1 kHz): vocal clarity and body");
        let pTreb  = eqp("TRE",-12,12,1,"dB",state.treble,"--treble","Treble (8 kHz): brightness, cymbals, air");
        let pPitch = eqp("PITCH",-12,12,1,"st",state.pitch,"--pitch","Pitch Shift: changes key without speed");
        let pWarp  = eqp("WARP",-100,100,10,"ct",state.warp,"--warp","Warp: analog tape pitch glide in cents");
        let pComp  = eqp("COMP",0,100,5,"%",state.compressor,"--compressor","Compressor: levels peaks and lifts quiet passages");
        let pLoud  = eqp("LOUD",0,100,5,"%",state.loudness,"--loudness","Loudness: equal-loudness bass/treble boost");
        let pChor  = eqp("CHOR",0,100,5,"%",state.chorus,"--chorus","Chorus: multi-voice doubling and stereo shimmer");
        let pRev   = eqp("REV",0,100,5,"%",state.reverb,"--reverb","Reverb: small-room acoustic depth");
        let pDel   = eqp("DEL",0,100,5,"%",state.delay,"--delay","Echo: repeat level");
        let pRevT  = mkp("REV TYPE",0,0,0,"",state.reverb_type,["room","plate","cath"],(v)=>EQC+" --reverb-type "+v,"Reverb character: room / plate / cathedral","reverb_type");
        let pDelT  = mkp("DEL DIV",0,0,0,"",state.delay_type,["slap","1/8","1/4","trip","ping"],(v)=>EQC+" --delay-type "+v,"Echo division: slap-back, note division, triplet, ping-pong","delay_type");
        let pChorT = mkp("CHOR VOX",0,0,0,"",state.chorus_type,["duet","trio","vib"],(v)=>EQC+" --chorus-type "+v,"Chorus voices: duet / trio / wide vibrato","chorus_type");
        let pMod   = eqp("FMOD",0,100,5,"%",state.modulator,"--modulator","Frequency Modulator: swept resonant focus");
        let pWide  = eqp("WIDE",0,100,5,"%",state.width,"--width","Stereo Width: expands field; past 50% adds surround crossfeed");
        let pBalLo = mkp("BAL·L",0,0,0,"",state.bal_low,["neutral","low","mid"],(v)=>EQC+" --bal-low "+v,"Freq. Bal.: tilt low band toward neutral/low/mid","bal_low");
        let pBalHi = mkp("BAL·H",0,0,0,"",state.bal_high,["neutral","mid","high"],(v)=>EQC+" --bal-high "+v,"Freq. Bal.: tilt high band toward neutral/mid/high","bal_high");
        this._outParams = [pBass,pMid,pTreb,pPitch,pWarp,pComp,pLoud,pChor,pRev,pMod,pWide,pDel];
        this._outDefaults = [0,0,0,0,0,0,0,0,0,0,0,0];

        // EQ band sub-params: center freq + Q (levers in the EQ detail editor)
        const mkf = (v,k,tip,mn,mx) => { let p = mkp("",mn,mx,0.5,"",v,null,(x)=>EQC+" "+k+" "+Math.round(x),tip,k.replace(/^--/,'').replace(/-/g,'_')); p.fmt = (x)=>Math.round(x)+"Hz"; return p; };
        const mkq = (v,k,tip) => { let p = mkp("",0.3,8,0.1,"",v,null,(x)=>EQC+" "+k+" "+x.toFixed(1),tip,k.replace(/^--/,'').replace(/-/g,'_')); p.fmt = (x)=>"Q "+x.toFixed(1); return p; };
        let eqMod = new LcdModule("EQ", [pBass,pMid,pTreb], this);
        eqMod.eqEditor = true;
        eqMod.eqBands = [
            { name: "BAS", kind: "low",  gain: pBass, freq: mkf(state.bass_freq,"--bass-freq","Bass shelf corner",20,500),       q: mkq(state.bass_q,"--bass-q","Bass shelf slope"),      fmin: 20,   fmax: 500 },
            { name: "MID", kind: "peak", gain: pMid,  freq: mkf(state.mid_freq,"--mid-freq","Mid peak center",200,8000),         q: mkq(state.mid_q,"--mid-q","Mid bandwidth"),           fmin: 200,  fmax: 8000 },
            { name: "TRE", kind: "high", gain: pTreb, freq: mkf(state.treble_freq,"--treble-freq","Treble shelf corner",1500,16000), q: mkq(state.treble_q,"--treble-q","Treble shelf slope"), fmin: 1500, fmax: 16000 },
        ];
        this._outParams.push(...eqMod.eqBands.flatMap(b => [b.freq, b.q]));
        this._outDefaults.push(100,1.0, 1000,1.0, 8000,1.0);

        eqMod.unitKey = "EQ";
        let pitchM = new LcdModule("PITCH", [pPitch,pWarp], this); pitchM.unitKey = "PITCH";
        let dynM   = new LcdModule("DYN", [pComp,pLoud], this); dynM.unitKey = "DYN";
        let spaceM = new LcdModule("SPACE", [pRev,pRevT,pDel,pDelT,pChor,pChorT], this,
                [{main:pRev,sub:pRevT},{main:pDel,sub:pDelT},{main:pChor,sub:pChorT}]); spaceM.unitKey = "SPACE";
        let modM   = new LcdModule("MOD", [pMod,pWide], this); modM.unitKey = "MOD";
        let tiltM  = new LcdModule("TILT", [pBalLo,pBalHi], this); tiltM.unitKey = "TILT";

        pair(eqMod, pitchM, leftCol);
        pair(dynM, spaceM, leftCol);
        pair(modM, tiltM, leftCol);

        // ---- master SCENE module: coordinates all units via composite presets ----
        let pScene = mkp("SCENE",0,0,0,"",Object.keys(this._presets.scenes)[0]||"FLAT",
            Object.keys(this._presets.scenes), null, "Composite preset: applies a named effect setting across all units");
        pScene.onAdj = (v) => this._applyScene(v);
        this._pScene = pScene;
        this.sceneMod = new LcdModule("SCENE", [pScene], this);
        this.sceneMod.isScene = true;
        this._modules.push(this.sceneMod);

        // FX engine toggle + reset
        let btnRow = new St.BoxLayout({ vertical: false, style: "spacing: 6px; margin-top: 4px;" });
        this.btnFxToggle = new St.Button({ style: `${RACK_BTN} padding: 2px 6px;` });
        this.fxLed = _ledDot(T.val, 6);
        this.fxLabel = new St.Label({ text: "FX: ON", y_align: St.Align.MIDDLE,
            style: `font-size: 8px; font-weight: bold; color: ${T.head};` });
        let fxRow = new St.BoxLayout({ style: "spacing: 4px;" });
        fxRow.add_actor(this.fxLed); fxRow.add_actor(this.fxLabel);
        this.btnFxToggle.set_child(fxRow);
        this.btnFxToggle.connect('clicked', () => {
            Util.spawnCommandLine(EQC + " --toggle-bypass");
            this._updateFxToggle();
        });
        this.btnReset = new St.Button({ style: `${RACK_BTN} padding: 2px 6px;` });
        let rstRow = new St.BoxLayout({ style: "spacing: 4px;" });
        rstRow.add_actor(_ledDot(T.acc, 6));
        rstRow.add_actor(new St.Label({ text: "RESET", y_align: St.Align.MIDDLE,
            style: `font-size: 8px; font-weight: bold; color: ${T.head};` }));
        this.btnReset.set_child(rstRow);
        this.btnReset.connect('clicked', () => {
            Util.spawnCommandLine(EQC + " --reset");
            this._outParams.forEach((p, i) => p.setVal(this._outDefaults[i]));
            pBalLo.setVal("neutral"); pBalHi.setVal("neutral");
            this._refreshAll();
        });
        btnRow.add_actor(this.btnFxToggle); btnRow.add_actor(this.btnReset);
        leftCol.add_actor(btnRow);
        this._updateFxToggle();

        // ================= divider =================
        let divider = new St.BoxLayout({ vertical: true, style: `width: 1px; background-color: ${T.div}; margin: 0px 2px;` });

        // ================= RIGHT: INPUT =================
        let rightCol = new St.BoxLayout({ vertical: true, x_expand: true, style: "spacing: 4px;" });
        rightCol.add_actor(new St.Label({ text: "🎛 INPUT", style: `font-size: 8.5px; font-weight: bold; color: ${T.head};` }));
        rightCol.add_actor(inVolItem.actor);

        let micState = { noise: 0, clarity: 0, voxpress: 0, drive: 0, echo: 0, voxrev: 0, aux: false };
        try {
            let [fres, fout] = GLib.spawn_command_line_sync(MXC + " --json");
            if (fres) micState = Object.assign(micState, JSON.parse(new TextDecoder().decode(fout)));
        } catch (e) {}

        let pNoise  = fxp("NCUT",micState.noise,"--noise","Noise Filter: gates out background noise below speech level");
        let pClar   = fxp("CLAR",micState.clarity,"--clarity","Clear Voice: 3 kHz presence boost plus low-rumble cut");
        let pVox    = fxp("VOX",micState.voxpress,"--voxpress","Vocal Compressor: levels loud and quiet speech");
        let pDrv    = fxp("DRV",micState.drive,"--drive","Drive: soft-clip saturation pedal");
        let pEcho   = fxp("ECHO",micState.echo,"--echo","Echo: slap-back delay repeat");
        let pVrev   = fxp("VREV",micState.voxrev,"--voxrev","Vocal Reverb: room ambience on the input");
        let pAux    = mkp("AUX IN",0,0,0,"",micState.aux ? "on" : "off",["off","on"],(v)=>MXC+" --aux "+v,"Virtual Input Port: apps play audio into the mic chain");

        pair(new LcdModule("CLEAN", [pNoise,pClar], this),
             new LcdModule("DYN", [pVox,pDrv], this), rightCol);
        pair(new LcdModule("SPACE", [pEcho,pVrev], this),
             new LcdModule("PORTS", [pAux], this), rightCol);

        // ================= detail view =================
        this.detailBox = new St.BoxLayout({
            vertical: true,
            style: `spacing: 2px; padding: 6px 8px; ${RACK_DEEP}`
        });
        this.detailBox.hide();

        container.add_actor(this.sceneMod.actor);
        colsRow.add_actor(leftCol);
        colsRow.add_actor(divider);
        colsRow.add_actor(rightCol);
        container.add_actor(colsRow);
        container.add_actor(this.detailBox);
        this.addActor(container, { expand: true, span: -1 });
    }

    toggleDetail(module) {
        if (this._openModule === module) {
            this._openModule = null;
            this._eqRefs = [];
            this._eqCurveUpdate = null;
            this._detailRows = [];
            this.detailBox.hide();
            return;
        }
        this._openModule = module;
        this._eqRefs = [];
        this._eqCurveUpdate = null;
        if (module.eqEditor)
            return this._buildEqDetail(module);
        this.detailBox.destroy_all_children();
        this._detailRows = [];

        let head = new St.BoxLayout({ style: "spacing: 6px; margin-bottom: 2px;" });
        head.add_actor(new St.Label({
            text: module.title,
            x_expand: true,
            style: `font-size: 11px; font-weight: bold; color: ${T.acc}; letter-spacing: 1px;`
        }));
        let btnClose = new St.Button({ label: "✕", style: `font-size: 10px; color: ${T.val}; padding: 0px 5px; border-radius: 4px; background-color: ${T.btnBg}; border: 1px solid ${T.cardBd};` });
        btnClose.connect('clicked', () => this.toggleDetail(module));
        head.add_actor(btnClose);
        this.detailBox.add_actor(head);
        this._addPresetRow(module);
        for (let p of module.params) {
            let row = new St.BoxLayout({ style: "spacing: 6px; padding: 1px 0px;" });
            row.add_actor(new St.Label({ text: p.name, style: `font-size: 10px; font-family: monospace; color: ${T.dim}; min-width: 56px;` }));
            let bm = new St.Button({ label: "−", style: `font-size: 13px; color: ${T.val}; padding: 0px 8px; border-radius: 4px; background-color: ${T.btnBg}; border: 1px solid ${T.cardBd};` });
            bm.connect('clicked', () => p.adj(-1));
            row.add_actor(bm);
            let lv = new St.Label({ text: "", x_expand: true, style: `font-size: 14px; font-family: monospace; font-weight: bold; color: ${T.val}; text-shadow: 0 0 6px ${T.valGlow}; text-align: center;` });
            row.add_actor(lv);
            this._detailRows.push({ param: p, label: lv });
            let bp = new St.Button({ label: "+", style: `font-size: 13px; color: ${T.val}; padding: 0px 8px; border-radius: 4px; background-color: ${T.btnBg}; border: 1px solid ${T.cardBd};` });
            bp.connect('clicked', () => p.adj(1));
            row.add_actor(bp);
            row.add_actor(new St.Label({ text: p.rangeText(), style: `font-size: 8px; font-family: monospace; color: ${T.dim2}; min-width: 64px; text-align: right;` }));
            row.reactive = true;
            row.connect('scroll-event', (a, e) => {
                let d = e.get_scroll_direction();
                if (d === Clutter.ScrollDirection.UP) p.adj(1);
                else if (d === Clutter.ScrollDirection.DOWN) p.adj(-1);
                return Clutter.EVENT_STOP;
            });
            this.detailBox.add_actor(row);
        }
        this._refreshDetail();
        this.detailBox.show();
    }

    // Bigger picture: EQ response curve + per-band F/G/Q levers
    _buildEqDetail(module) {
        this.detailBox.destroy_all_children();
        this._detailRows = [];
        this._eqRefs = [];

        let head = new St.BoxLayout({ style: "spacing: 6px; margin-bottom: 2px;" });
        head.add_actor(new St.Label({
            text: module.title + "  —  response",
            x_expand: true,
            style: `font-size: 11px; font-weight: bold; color: ${T.acc}; letter-spacing: 1px;`
        }));
        let btnClose = new St.Button({ label: "✕", style: `font-size: 10px; color: ${T.val}; padding: 0px 5px; border-radius: 4px; background-color: ${T.btnBg}; border: 1px solid ${T.cardBd};` });
        btnClose.connect('clicked', () => this.toggleDetail(module));
        head.add_actor(btnClose);
        this.detailBox.add_actor(head);
        this._addPresetRow(module);

        // --- response curve: 30 bars, 20 Hz .. 20 kHz log ---
        const NBARS = 30, BARH = 44;
        let curveBox = new St.BoxLayout({ style: `spacing: 1px; height: 50px; padding: 3px 3px 2px 3px; border-bottom: 1px solid ${T.cardBd}; margin-bottom: 4px;` });
        let bars = [];
        for (let i = 0; i < NBARS; i++) {
            let b = new St.Widget({ style: `width: 7px; height: 2px; background-color: ${T.eqBar}; border-radius: 1px;`, x_expand: true, y_align: Clutter.ActorAlign.END });
            curveBox.add_actor(b);
            bars.push(b);
        }
        this.detailBox.add_actor(curveBox);

        const updateCurve = () => {
            for (let i = 0; i < NBARS; i++) {
                let f = 20 * Math.pow(1000, i / (NBARS - 1));
                let db = 0;
                for (let band of module.eqBands)
                    db += _eqBandDb(band.kind, band.freq.value, band.q.value, band.gain.value, f);
                let h = Math.round(Math.max(0.02, Math.min(1, (db + 12) / 24)) * BARH);
                bars[i].set_height(Math.max(2, h));
            }
        };
        this._eqCurveUpdate = updateCurve;

        // --- per-band lever rows: name | F slider+val | G slider+val | Q slider+val ---
        const mkLever = (param, toNorm, fromNorm, widthHint) => {
            let grp = new St.BoxLayout({ style: "spacing: 3px;" });
            let sl = new Slider.Slider(toNorm(param.value));
            sl.actor.x_expand = true;
            sl.connect('value-changed', (a, v) => param.setTo(fromNorm(v)));
            let lv = new St.Label({ text: "", style: "font-size: 9px; font-family: monospace; color: " + T.val + "; min-width: " + widthHint + "px; text-align: right;" });
            grp.add_actor(sl.actor);
            grp.add_actor(lv);
            this._eqRefs.push({ slider: sl, param: param, toNorm: toNorm, label: lv });
            return grp;
        };

        for (let band of module.eqBands) {
            let row = new St.BoxLayout({ style: "spacing: 6px; padding: 2px 0px;" });
            row.add_actor(new St.Label({ text: band.name, style: `font-size: 10px; font-family: monospace; font-weight: bold; color: ${T.dim}; min-width: 30px; padding-top: 4px;` }));
            let logN = (v, mn, mx) => Math.log(v / mn) / Math.log(mx / mn);
            let unLog = (v, mn, mx) => mn * Math.pow(mx / mn, v);
            row.add_actor(mkLever(band.freq, (v) => logN(v, band.fmin, band.fmax), (v) => unLog(v, band.fmin, band.fmax), 52));
            row.add_actor(mkLever(band.gain, (v) => (v + 12) / 24, (v) => v * 24 - 12, 46));
            row.add_actor(mkLever(band.q, (v) => logN(v, 0.3, 8), (v) => unLog(v, 0.3, 8), 34));
            new Tooltips.Tooltip(row, band.name + ": drag levers — F=frequency, G=gain, Q=width");
            this.detailBox.add_actor(row);
        }
        let hint = new St.Label({ text: "levers:  FREQ  ·  GAIN  ·  Q    per band", style: `font-size: 8px; font-family: monospace; color: ${T.dim2}; text-align: center;` });
        this.detailBox.add_actor(hint);

        this._refreshDetail();
        this.detailBox.show();
    }

    // ---- presets ----
    _presetNames(module) {
        if (module.isScene) return Object.keys(this._presets.scenes);
        if (module.unitKey) return Object.keys((this._presets.units || {})[module.unitKey] || {});
        return [];
    }

    _applyNamedPreset(module, name) {
        this._showEdu(module, name);
        if (module.isScene) this._applyScene(name);
        else this._applyUnitPreset(module.unitKey, name);
    }

    _addPresetRow(module) {
        const EQC = "/home/lumba/.local/bin/set-eq";
        if (!module.isScene && !module.unitKey) return;

        let row = new St.BoxLayout({ style: "spacing: 4px; margin-bottom: 2px;" });
        row.add_actor(new St.Label({ text: module.isScene ? "SCENE" : "PRESET",
            style: `font-size: 8px; font-family: monospace; color: ${T.dim}; padding-top: 4px;` }));

        // dropdown button showing current selection
        module._ddButton = new St.Button({
            label: (module._lastPreset || "— select —") + "  ▾",
            x_expand: true,
            style: `font-size: 9px; font-family: monospace; color: ${T.val}; padding: 3px 8px; border-radius: 4px; background-color: ${T.btnBg}; border: 1px solid ${T.cardBd}; text-align: left;`
        });
        module._ddButton.connect('clicked', () => this._togglePresetDropdown(module));
        row.add_actor(module._ddButton);

        // + button: save current settings under a custom name
        let plus = new St.Button({ label: "＋",
            style: `font-size: 11px; font-family: monospace; color: ${T.acc}; padding: 1px 8px; border-radius: 4px; background-color: ${T.btnBg}; border: 1px solid ${T.cardBd};` });
        plus.connect('clicked', () => this._saveName((n) => {
            if (module.isScene) Util.spawnCommandLine(EQC + ' --save-preset "' + n + '"');
            else Util.spawnCommandLine(EQC + ' --save-unit-preset "' + module.unitKey + '" "' + n + '"');
            module._lastPreset = n;
            this._reloadPresets();
            this._reopenDetail(module);
        }));
        row.add_actor(plus);
        this.detailBox.add_actor(row);

        // collapsible dropdown list, opened by the ▾ button
        module._ddBox = new St.BoxLayout({ vertical: true,
            style: `margin: 0px 0px 4px 42px; padding: 2px; border-radius: 4px; background-color: ${T.ddBg}; border: 1px solid ${T.cardBd};` });
        module._ddBox.hide();
        this.detailBox.add_actor(module._ddBox);

        // edutainment: commentary line explaining the selected preset
        module._eduLabel = new St.Label({
            text: this._eduFor(module, module._lastPreset) || "",
            style: `width: 380px; font-size: 8.5px; font-family: monospace; color: ${T.dim}; font-style: italic; margin: 2px 0px 4px 0px;`
        });
        module._eduLabel.clutter_text.line_wrap = true;
        this.detailBox.add_actor(module._eduLabel);

        if (module.isScene) this._addSceneGrid(module);
    }

    _eduFor(module, name) {
        if (!name || !this._presets.edu) return "";
        if (module.isScene) return (this._presets.edu.scenes || {})[name] || "";
        return (((this._presets.edu.units || {})[module.unitKey]) || {})[name] || "";
    }

    _showEdu(module, name) {
        module._lastPreset = name || module._lastPreset;
        if (module._eduLabel) module._eduLabel.text = this._eduFor(module, name) || "";
        if (module._ddButton && name) module._ddButton.label = name + "  ▾";
    }

    // XY scene matrix: collapsible category headers x compact preset tiles (4 per row)
    _addSceneGrid(module) {
        const ORDER = ["METAL","ROCK","DRUMS","VOCAL","URBAN","ELECTRONIC","DREAM","SPACES","UTILITY","CUSTOM"];
        let cats = this._presets.cats || {};
        let curCat = cats[this._pScene ? this._pScene.value : ""] || "CUSTOM";
        let wrap = new St.BoxLayout({ vertical: true, style: "margin-top: 4px;" });
        for (let cat of ORDER) {
            let names = Object.keys(this._presets.scenes).filter(n => (cats[n] || "CUSTOM") === cat);
            if (!names.length) continue;
            let grid = new St.BoxLayout({ vertical: true });
            for (let i = 0; i < names.length; i += 4) {
                let row = new St.BoxLayout({ style: "spacing: 3px; margin-top: 2px;" });
                for (let n of names.slice(i, i + 4)) {
                    let t = new St.Button({ label: n,
                        style: `width: 96px; font-size: 8px; font-family: monospace; color: ${T.val}; padding: 4px 2px; border-radius: 3px; background-color: ${T.btnBg}; border: 1px solid ${T.cardBd}; text-align: center;` });
                    t.connect('enter-event', () => t.add_style_pseudo_class('hover'));
                    t.connect('leave-event', () => t.remove_style_pseudo_class('hover'));
                    t.connect('clicked', () => this._applyScene(n));
                    row.add_actor(t);
                }
                grid.add_actor(row);
            }
            grid.visible = (cat === curCat);
            let head = new St.Button({ label: (cat === curCat ? "─ " + cat + " ▾" : "─ " + cat + " ▸"),
                x_align: St.Align.START,
                style: `width: 110px; font-size: 8px; font-family: monospace; color: ${T.acc}; letter-spacing: 2px; margin-top: 4px; padding: 1px 6px; text-align: left;` });
            head.connect('clicked', () => {
                grid.visible = !grid.visible;
                head.label = (grid.visible ? "─ " + cat + " ▾" : "─ " + cat + " ▸");
            });
            wrap.add_actor(head);
            wrap.add_actor(grid);
        }
        this.detailBox.add_actor(wrap);
    }

    _togglePresetDropdown(module) {
        let box = module._ddBox;
        if (!box) return;
        if (box.visible) { box.hide(); return; }
        box.destroy_all_children();
        let names = this._presetNames(module);
        if (!names.length) {
            box.add_actor(new St.Label({ text: "  no presets saved — press ＋",
                style: `font-size: 9px; font-family: monospace; color: ${T.dim}; padding: 3px;` }));
        }
        // compact 3-wide tile grid instead of a long full-width list
        for (let i = 0; i < names.length; i += 3) {
            let r = new St.BoxLayout({ style: "spacing: 3px;" });
            for (let name of names.slice(i, i + 3)) {
                let it = new St.Button({ label: name, x_expand: true,
                    style: `font-size: 8.5px; font-family: monospace; color: ${T.val}; padding: 4px 2px; border-radius: 3px; text-align: center;` });
                it.connect('enter-event', () => it.add_style_pseudo_class('hover'));
                it.connect('leave-event', () => it.remove_style_pseudo_class('hover'));
                it.connect('clicked', () => {
                    this._applyNamedPreset(module, name);
                    box.hide();
                });
                r.add_actor(it);
            }
            box.add_actor(r);
        }
        box.show();
    }

    _reopenDetail(module) {
        this._openModule = null;
        this.toggleDetail(module);
    }

    _applyScene(name) {
        if (this._pScene) { this._pScene.value = name; this._refreshAll(); }
        if (this.sceneMod) this._showEdu(this.sceneMod, name);
        Util.spawnCommandLine('/home/lumba/.local/bin/set-eq --preset "' + name + '"');
        Mainloop.timeout_add(180, () => { this._resyncState(); return false; });
    }

    _applyUnitPreset(unit, name) {
        Util.spawnCommandLine('/home/lumba/.local/bin/set-eq --unit-preset "' + unit + '" "' + name + '"');
        Mainloop.timeout_add(180, () => { this._resyncState(); return false; });
    }

    _resyncState() {
        try {
            let [res, out] = GLib.spawn_command_line_sync("/home/lumba/.local/bin/set-eq --json");
            if (!res) return;
            let st = JSON.parse(new TextDecoder().decode(out));
            for (let p of this._allParams)
                if (p.stateKey && st[p.stateKey] !== undefined) p.setVal(st[p.stateKey]);
            this._refreshAll();
        } catch (e) {}
    }

    _reloadPresets() {
        try {
            let [r, o] = GLib.spawn_command_line_sync("/home/lumba/.local/bin/set-eq --presets-json");
            if (r) this._presets = Object.assign({scenes:{},units:{},cats:{}}, JSON.parse(new TextDecoder().decode(o)));
            if (this._pScene) this._pScene.choices = Object.keys(this._presets.scenes);
        } catch (e) {}
    }

    _saveName(cb) {
        Util.spawn_async(['zenity', '--entry', '--title', 'Save preset', '--text', 'Preset name:'],
            (out) => { let n = (out || '').trim(); if (n) cb(n); });
    }

    _refreshAll() {
        for (let m of this._modules) m.refresh();
        this._refreshDetail();
    }

    _refreshDetail() {
        for (let r of this._detailRows)
            r.label.set_text(r.param.disp());
        if (this._eqRefs) {
            for (let r of this._eqRefs) {
                r.slider.setValue(r.toNorm(r.param.value));
                r.label.set_text(r.param.disp());
            }
        }
        if (this._eqCurveUpdate)
            this._eqCurveUpdate();
    }

    _updateFxToggle() {
        Util.spawn_async(['/home/lumba/.local/bin/set-eq', '--json'], (out) => {
            try {
                let st = JSON.parse(out);
                let on = !st.bypass;
                this.fxLabel.text = on ? "FX: ON" : "FX: OFF";
                this.fxLed.style = "width: 6px; height: 6px; border-radius: 3px; background-color: " +
                    (on ? T.val : T.hint) + "; box-shadow: 0 0 6px " + (on ? T.val : "transparent") + ";";
            } catch (e) {}
        });
    }
}

class Seeker extends Slider.Slider {
    constructor(mediaServerPlayer, props, playerName) {
        super(0, true);
        this.actor.set_direction(St.TextDirection.LTR); //Do not invert on RTL layout

        this.canSeek = true;
        this.status = 'Stopped';
        this._wantedSeekValue = 0;

        this._currentTime = 0;
        this._length = 0;
        this._trackid = "";

        this._timeoutId = 0;
        this._timerTicker = 0;

        this._mediaServerPlayer = mediaServerPlayer;
        this._prop = props;
        this._playerName = playerName;

        this.connect('drag-end', () => { this._setPosition() });
        this.connect('value-changed', () => {
            if(!this._dragging) // Update on scroll events
                this._setPosition();
        });

        this._seekChangedId = mediaServerPlayer.connectSignal('Seeked', (id, sender, value) => {
            // Seek value sent by the player
            if (value > 0) {
                this._setPosition(value);
            }
            // Seek initiated by the position slider
            else if (this._wantedSeekValue > 0) {
                // Some broken gstreamer players (Banshee) reports always 0
                // when the track is seeked so we set the position at the
                // value we set on the slider
                this._setPosition(this._wantedSeekValue);
            }
            else {
                // Some players send negative values (Rhythmbox).
                // Only positive values or zero are allowed.
                this._setPosition(0);
            }

            this._wantedSeekValue = 0;
        });

        this._getCanSeek();
    }

    play() {
        this.status = 'Playing';
        this._getCanSeek();
    }

    pause() {
        this.status = 'Paused';
        this._updateTimer();
    }

    stop() {
        this.status = 'Stopped';
        this._updateTimer();
    }

    setTrack(trackid, length) {
        this._trackid = trackid;
        this._length = length;
        this._currentTime = 0;
        this._updateValue();
    }

    _updateValue() {
        if (!this._dragging && this.canSeek) {
            if (this._length > 0 && this._currentTime > 0)
                this.setValue(this._currentTime / this._length);
            else
                this.setValue(0);
        }
    }

    _timerCallback() {
        if (this.status === 'Playing') {
            if (this._timerTicker < 10) {
                this._currentTime += 1;
                this._timerTicker++;
                this._updateValue();
            } else { // Sync every 10 ticks
                this._timerTicker = 0;
                this._getPosition();
            }
            return GLib.SOURCE_CONTINUE;
        }

        this._timeoutId = 0;
        return GLib.SOURCE_REMOVE;
    }

    _updateTimer() {
        if (this._timeoutId > 0) {
            Mainloop.source_remove(this._timeoutId);
            this._timeoutId = 0;
        }

        if (this.status === 'Playing') {
            if (this.canSeek) {
                this._getPosition();
                this._timerTicker = 0;
                this._timeoutId = Mainloop.timeout_add_seconds(1, this._timerCallback.bind(this));
            }
        } else {
            if (this.status === 'Stopped')
                this._currentTime = 0;
            this._updateValue();
        }
    }

    _getCanSeek() {
        // Some players say they "CanSeek" but don't actually give their position over dbus
        if (players_without_seek_support.indexOf(this._playerName) > -1) {
            this._setCanSeek(false);
            return;
        }

        this._prop.GetRemote(MEDIA_PLAYER_2_PLAYER_NAME, 'CanSeek', (position, error) => {
            if (!error)
                this._setCanSeek(position[0].get_boolean());
        });
    }

    _setCanSeek(seek) {
        let playback_rate = this._mediaServerPlayer.Rate;
        // Hide seek for non-standard speeds except: 0 may mean paused, Audacious returns null
        if (seek && (playback_rate === 1 || !playback_rate)) {
            this.canSeek = true;
            this.actor.show();
            this._updateTimer();
        } else {
            this.canSeek = false;
            this.actor.hide();
        }
    }

    _setPosition(value) {
        if(value >= 0) {
            this._currentTime = value / 1000000;
            this._updateValue();
        } else {
            let time = this._value * this._length * 1000000;
            this._wantedSeekValue = Math.round(time);
            this._mediaServerPlayer.SetPositionRemote(this._trackid, time);
        }
    }

    _getPosition() {
        this._prop.GetRemote(MEDIA_PLAYER_2_PLAYER_NAME, 'Position', (position, error) => {
            if (!error)
                this._setPosition(position[0].get_int64());
        });
    }

    destroy() {
        if (this._timeoutId > 0) {
            Mainloop.source_remove(this._timeoutId);
            this._timeoutId = 0;
        }
        if (this._seekChangedId) {
            this._mediaServerPlayer.disconnectSignal(this._seekChangedId);
            this._seekChangedId = 0;
        }

        this.disconnectAll();
        this._mediaServerPlayer = null;
        this._prop = null;
    }
}

class StreamMenuSection extends PopupMenu.PopupMenuSection {
    constructor(applet, stream) {
        super();

        let iconName = stream.icon_name;
        let name = stream.name;

        // capitalize the stream name
        if (name.length > 2) {
            name = name.charAt(0).toUpperCase() + name.slice(1);
        }

        // Trim stream name
        if(name.length > 20) {
            name = name.substring(0, 16) + "... ";
        }

        // Special cases
        if (name === "Banshee") {
            iconName = "banshee";
        }
        else if (name === "Spotify") {
            iconName = "spotify";
        }
        else if (name === "VBox") {
            name = "Virtualbox";
            iconName = "virtualbox";
        }
        else if (name === "Firefox") {
            iconName = "firefox";
        }
        else if (iconName === "audio") {
            iconName = "audio-x-generic";
        }

        // Prevent Muffin from spawning sound streams
        if (name !== "Muffin") {
            let slider = new VolumeSlider(applet, stream, name, iconName);
            slider._slider.style = "min-width: 6em;";
            this.addMenuItem(slider);
        }
    }
}

class Player extends PopupMenu.PopupMenuSection {
    constructor(applet, busname, owner) {
        super();
        this._owner = owner;
        this._busName = busname;
        this._applet = applet;

        // We'll update this later with a proper name
        this._name = this._busName;

        let asyncReadyCb = (proxy, error, property) => {
            if (error)
                log(error);
            else {
                this[property] = proxy;
                this._dbus_acquired();
            }
        };

        Interfaces.getDBusProxyWithOwnerAsync(MEDIA_PLAYER_2_NAME,
                                              this._busName,
                                              (p, e) => asyncReadyCb(p, e, '_mediaServer'));

        Interfaces.getDBusProxyWithOwnerAsync(MEDIA_PLAYER_2_PLAYER_NAME,
                                              this._busName,
                                              (p, e) => asyncReadyCb(p, e, '_mediaServerPlayer'));

        Interfaces.getDBusPropertiesAsync(this._busName,
                                          MEDIA_PLAYER_2_PATH,
                                          (p, e) => asyncReadyCb(p, e, '_prop'));

    }

    _dbus_acquired() {
        if (!this._prop || !this._mediaServerPlayer || !this._mediaServer)
            return;

        if (this._mediaServer.Identity) {
            this._name = this._mediaServer.Identity;
        } else {
            let displayName = this._busName.replace('org.mpris.MediaPlayer2.', '');
            this._name = displayName.capitalize();
        }

        let mainBox = new PopupMenu.PopupMenuSection();
        this.addMenuItem(mainBox);

        this.vertBox = new St.BoxLayout({ style_class: "sound-player", important: true, vertical: true });
        mainBox.addActor(this.vertBox, { expand: false });

        // Player info
        this._playerBox = new St.BoxLayout();
        this.playerIcon = new St.Icon({icon_type: St.IconType.SYMBOLIC, style_class: "popup-menu-icon"});
        this.playerLabel = new St.Label({
            y_expand: true, y_align: Clutter.ActorAlign.CENTER,
            x_expand: true, x_align: Clutter.ActorAlign.START
        });

        this._playerBox.add_actor(this.playerIcon);
        this._playerBox.add_actor(this.playerLabel);

        if (this._mediaServer.CanRaise) {
            this._showCanRaise();
        }
        if (this._mediaServer.CanQuit) {
            this._showCanQuit();
        }

        this.vertBox.add_actor(this._playerBox);

        // Cover Box (art + track info)
        this._trackCover = new St.Bin({x_align: St.Align.MIDDLE});
        this._trackCoverFile = this._trackCoverFileTmp = false;
        this.coverBox = new Clutter.Box();
        let l = new Clutter.BinLayout({x_align: Clutter.BinAlignment.FILL, y_align: Clutter.BinAlignment.END});
        this.coverBox.set_layout_manager(l);

        // Cover art
        this.cover = new St.Icon({icon_name: "media-optical", icon_size: 300, icon_type: St.IconType.FULLCOLOR});
        this.coverBox.add_actor(this.cover);

        this._cover_load_handle = 0;
        this._cover_path = null;

        // Track info (artist + title)
        this._artist = _("Unknown Artist");
        this._album = _("Unknown Album");
        this._title = _("Unknown Title");
        this.trackInfo = new St.BoxLayout({style_class: 'sound-player-overlay', important: true, vertical: true});
        let artistInfo = new St.BoxLayout();
        let artistIcon = new St.Icon({ icon_type: St.IconType.SYMBOLIC, icon_name: "xsi-users", style_class: 'popup-menu-icon' });
        this.artistLabel = new St.Label({text:this._artist});
        this.artistLabel.clutterText.line_wrap = true;
        this.artistLabel.clutterText.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        this.artistLabel.clutterText.ellipsize = Pango.EllipsizeMode.NONE;
        artistInfo.add_actor(artistIcon);
        artistInfo.add_actor(this.artistLabel);
        let titleInfo = new St.BoxLayout();
        let titleIcon = new St.Icon({ icon_type: St.IconType.SYMBOLIC, icon_name: "xsi-audio-x-generic", style_class: 'popup-menu-icon' });
        this.titleLabel = new St.Label({text:this._title});
        this.titleLabel.clutterText.line_wrap = true;
        this.titleLabel.clutterText.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        this.titleLabel.clutterText.ellipsize = Pango.EllipsizeMode.NONE;
        titleInfo.add_actor(titleIcon);
        titleInfo.add_actor(this.titleLabel);
        this.trackInfo.add_actor(artistInfo);
        this.trackInfo.add_actor(titleInfo);
        this.coverBox.add_actor(this.trackInfo);

        this._trackCover.set_child(this.coverBox);
        this.vertBox.add_actor(this._trackCover);

        // Playback controls
        let trackControls = new St.Bin({x_align: St.Align.MIDDLE});
        this._prevButton = new ControlButton("xsi-media-skip-backward",
                                             _("Previous"),
                                             () => this._mediaServerPlayer.PreviousRemote());
        this._playButton = new ControlButton("xsi-media-playback-start",
                                             _("Play"),
                                             () => this._mediaServerPlayer.PlayPauseRemote());
        this._stopButton = new ControlButton("xsi-media-playback-stop",
                                             _("Stop"),
                                             () => this._mediaServerPlayer.StopRemote());
        this._nextButton = new ControlButton("xsi-media-skip-forward",
                                             _("Next"),
                                             () => this._mediaServerPlayer.NextRemote());
        this.trackInfo.add_actor(trackControls);

        this.controls = new St.BoxLayout();
        if(St.Widget.get_default_direction () === St.TextDirection.RTL)
            this.controls.set_pack_start(true)

        this.controls.add_actor(this._prevButton.getActor());
        this.controls.add_actor(this._playButton.getActor());
        this.controls.add_actor(this._stopButton.getActor());
        this.controls.add_actor(this._nextButton.getActor());
        trackControls.set_child(this.controls);

        this._loopButton = new ControlButton("xsi-media-playlist-consecutive", _("Consecutive Playing"), () => this._toggleLoopStatus());
        this.controls.add_actor(this._loopButton.getActor());

        this._shuffleButton = new ControlButton("xsi-media-playlist-shuffle", _("No Shuffle"), () => this._toggleShuffle());
        this.controls.add_actor(this._shuffleButton.getActor());

        // Position slider
        this._seeker = new Seeker(this._mediaServerPlayer, this._prop, this._name.toLowerCase());
        this.vertBox.add_actor(this._seeker.actor);

        this._applet._updatePlayerMenuItems();

        this._setStatus(this._mediaServerPlayer.PlaybackStatus);
        this._setMetadata(this._mediaServerPlayer.Metadata);

        this._propChangedId = this._prop.connectSignal('PropertiesChanged', (proxy, sender, [iface, props]) => {
            if (props.PlaybackStatus)
                this._setStatus(props.PlaybackStatus.unpack());
            if (props.Metadata)
                this._setMetadata(props.Metadata.deep_unpack());
            if (props.CanGoNext || props.CanGoPrevious)
                this._updateControls();
            if (props.LoopStatus)
                this._setLoopStatus(props.LoopStatus.unpack());
            if (props.Shuffle)
                this._setShuffle(props.Shuffle.unpack());
            if (props.Identity) {
                this._name = props.Identity.unpack();
                this._applet._updatePlayerMenuItems();
            }
            if (props.CanRaise) {
                this._showCanRaise();
            }
            if (props.CanQuit) {
                this._showCanQuit();
            }
            if (props.DesktopEntry) {
                this._applet.passDesktopEntry(props.DesktopEntry.unpack());
            }
        });

        this._setLoopStatus(this._mediaServerPlayer.LoopStatus);
        this._setShuffle(this._mediaServerPlayer.Shuffle);

        if (this._mediaServer.DesktopEntry) {
            this._applet.passDesktopEntry(this._mediaServer.DesktopEntry);
        }
    }

    _showCanRaise() {
        let btn = new ControlButton("xsi-go-up", _("Open Player"), () => {
            if (this._name.toLowerCase() === "spotify") {
                // Spotify isn't able to raise via Dbus once its main UI is closed
                Util.spawn(['spotify']);
            }
            else {
                this._mediaServer.RaiseRemote();
            }
            this._applet.menu.close();
        }, true);
        this._playerBox.add_actor(btn.actor);
    }

    _showCanQuit() {
        let btn = new ControlButton("xsi-window-close", _("Quit Player"), () => {
            this._mediaServer.QuitRemote();
            this._applet.menu.close();
        }, true);
        this._playerBox.add_actor(btn.actor);
    }

    _setName(status) {
        this.playerLabel.set_text(this._name + " - " + _(status));
    }

    _updateControls() {
        this._prop.GetRemote(MEDIA_PLAYER_2_PLAYER_NAME, 'CanGoNext', (value, error) => {
            let canGoNext = false;
            if (!error)
                canGoNext = value[0].unpack();
            this._nextButton.setEnabled(canGoNext);
        });

        this._prop.GetRemote(MEDIA_PLAYER_2_PLAYER_NAME, 'CanGoPrevious', (value, error) => {
            let canGoPrevious = false;
            if (!error)
                canGoPrevious = value[0].unpack();
            this._prevButton.setEnabled(canGoPrevious);
        });
    }

    _setMetadata(metadata) {
        if (!metadata)
            return;

        let trackid = "";  // D-Bus path: A unique identity for this track
        if (metadata["mpris:trackid"]) {
            trackid = metadata["mpris:trackid"].unpack();
        }

        let trackLength = 0; // Track length in secs
        if (metadata["mpris:length"]) {
            trackLength = metadata["mpris:length"].unpack() / 1000000;
        }
        this._seeker.setTrack(trackid, trackLength);

        if (metadata["xesam:artist"]) {
            switch (metadata["xesam:artist"].get_type_string()) {
                case 's':
                    // smplayer sends a string
                    this._artist = metadata["xesam:artist"].unpack();
                    break;
                case 'as':
                    // others send an array of strings
                    this._artist = metadata["xesam:artist"].deep_unpack().join(", ");
                    break;
                default:
                    this._artist = _("Unknown Artist");
            }
            // make sure artist isn't empty
            if (!this._artist) this._artist = _("Unknown Artist");
        }
        else
            this._artist = _("Unknown Artist");

        this.artistLabel.set_text(this._artist);

        if (metadata["xesam:album"])
            this._album = metadata["xesam:album"].unpack();
        else
            this._album = _("Unknown Album");

        if (metadata["xesam:title"])
            this._title = metadata["xesam:title"].unpack();
        else
            this._title = _("Unknown Title");
        this.titleLabel.set_text(this._title);

        let change = false;
        if (metadata["mpris:artUrl"]) {
            let artUrl = metadata["mpris:artUrl"].unpack();
            if (this._trackCoverFile != artUrl) {
                this._trackCoverFile = artUrl;
                change = true;
            }
        }
        else {
            if (this._trackCoverFile != false) {
                this._trackCoverFile = false;
                change = true;
            }
        }

        if (change) {
            if (this._trackCoverFile) {
                let cover_path = "";
                if (this._trackCoverFile.match(/^http/)) {
                    if (!this._trackCoverFileTmp)
                        this._trackCoverFileTmp = Gio.file_new_tmp('XXXXXX.mediaplayer-cover')[0];
                    Util.spawn_async(['wget', this._trackCoverFile, '-O', this._trackCoverFileTmp.get_path()], () => this._onDownloadedCover());
                }
                else if (this._trackCoverFile.match(/data:image\/(png|jpeg);base64,/)) {
                    if (!this._trackCoverFileTmp)
                        this._trackCoverFileTmp = Gio.file_new_tmp('XXXXXX.mediaplayer-cover')[0];
                    const cover_base64 = this._trackCoverFile.split(',')[1];
                    const base64_decode = data => new Promise(resolve => resolve(GLib.base64_decode(data)));
                    if (!cover_base64) {
                        return;
                    }
                    base64_decode(cover_base64)
                    .then(decoded => {
                        this._trackCoverFileTmp.replace_contents(
                            decoded,
                            null,
                            false,
                            Gio.FileCreateFlags.REPLACE_DESTINATION,
                            null
                        );
                        return this._trackCoverFileTmp.get_path();
                    })
                    .then(path => this._showCover(path));
                }
                else {
                    cover_path = decodeURIComponent(this._trackCoverFile);
                    cover_path = cover_path.replace("file://", "");
                    this._showCover(cover_path);
                }
            }
            else
                this._showCover(false);
        }
        this._applet.setAppletTextIcon(this, true);
    }

    _setStatus(status) {
        if (!status)
            return;
        this._playerStatus = status;
        if (status == "Playing") {
            this._playButton.setData("xsi-media-playback-pause", _("Pause"));
            this.playerIcon.set_icon_name("xsi-media-playback-start");
            this._applet.setAppletTextIcon(this, true);
            this._seeker.play();
        }
        else if (status == "Paused") {
            this._playButton.setData("xsi-media-playback-start", _("Play"));
            this.playerIcon.set_icon_name("xsi-media-playback-pause");
            this._applet.setAppletTextIcon(this, false);
            this._seeker.pause();
        }
        else if (status == "Stopped") {
            this._playButton.setData("xsi-media-playback-start", _("Play"));
            this.playerIcon.set_icon_name("xsi-media-playback-stop");
            this._applet.setAppletTextIcon(this, false);
            this._seeker.stop();
        } else {
            this._applet.setAppletTextIcon(this, false);
        }

        this._setName(status);
    }

    _toggleLoopStatus() {
        let mapping = {
            "None": "Playlist",
            "Playlist": "Track",
            "Track": "None"
        };

        this._mediaServerPlayer.LoopStatus = mapping[this._mediaServerPlayer.LoopStatus];
        this._setLoopStatus(this._mediaServerPlayer.LoopStatus);
    }

    _setLoopStatus(status) {
        this._loopButton.actor.visible = this._applet.extendedPlayerControl && this._mediaServerPlayer.LoopStatus;

        if(status === "None")
            this._loopButton.setData("xsi-media-playlist-consecutive-symbolic", _("Consecutive Playing"));
        else if(status === "Track")
            this._loopButton.setData("xsi-media-playlist-repeat-song", _("Repeat Single"));
        else if(status === "Playlist")
            this._loopButton.setData("xsi-media-playlist-repeat", _("Repeat All"));

        this._loopButton.setActive(status !== "None");
    }

    _toggleShuffle() {
        this._mediaServerPlayer.Shuffle = !this._mediaServerPlayer.Shuffle;
    }

    _setShuffle(status) {
        this._shuffleButton.actor.visible = this._applet.extendedPlayerControl && this._mediaServerPlayer.Shuffle;

        this._shuffleButton.setData("xsi-media-playlist-shuffle", status? _("Shuffle") : _("No Shuffle"));
        this._shuffleButton.setActive(status);
    }

    _onDownloadedCover() {
        let cover_path = this._trackCoverFileTmp.get_path();
        this._showCover(cover_path);
    }

    _showCover(cover_path) {
        if (! cover_path || ! GLib.file_test(cover_path, GLib.FileTest.EXISTS)) {
            this.cover = new St.Icon({style_class: 'sound-player-generic-coverart', important: true, icon_name: "media-optical", icon_size: 300, icon_type: St.IconType.FULLCOLOR});
            this._cover_path = null;
            this._applet.setAppletTextIcon(this, null);
        }
        else {
            this._cover_path = cover_path;
            this._cover_load_handle = St.TextureCache.get_default().load_image_from_file_async(cover_path, 300, 300, this._on_cover_loaded.bind(this));
        }
    }

    _on_cover_loaded(cache, handle, actor) {
        if (handle !== this._cover_load_handle) {
            // Maybe a cover image load stalled? Make sure our requests match the callback.
            return;
        }

        this.coverBox.remove_actor(this.cover);

        // Make sure any oddly-shaped album art doesn't affect the height of the applet popup
        // (and move the player controls as a result).
        actor.margin_bottom = 300 - actor.height;

        this.cover = actor;
        this.coverBox.add_actor(this.cover);
        this.coverBox.set_child_below_sibling(this.cover, this.trackInfo);
        this._applet.setAppletTextIcon(this, this._cover_path);
    }

    onSettingsChanged() {
        this._loopButton.actor.visible = this._applet.extendedPlayerControl && this._mediaServerPlayer.LoopStatus;
        this._shuffleButton.actor.visible = this._applet.extendedPlayerControl && this._mediaServerPlayer.Shuffle;
    }

    destroy() {
        this._seeker.destroy();
        if (this._prop)
            this._prop.disconnectSignal(this._propChangedId);

        PopupMenu.PopupMenuSection.prototype.destroy.call(this);
    }
}

class MediaPlayerLauncher extends PopupMenu.PopupBaseMenuItem {
    constructor(app, menu) {
        super({});

        this._app = app;
        this._menu = menu;
        this.label = new St.Label({ text: app.get_name() });
        this.addActor(this.label);
        this._icon = app.create_icon_texture(ICON_SIZE);
        this._icon_bin = new St.Bin({ x_align: St.Align.END, child: this._icon });
        this.addActor(this._icon_bin, { expand: true, span: -1, align: St.Align.END });

        this.connect("activate", (event) => this._onActivate(event));
    }

    _onActivate(event) {
        let _time = event.time;
        this._app.activate_full(-1, _time);
    }
}

class CinnamonSoundApplet extends Applet.TextIconApplet {
    constructor(metadata, orientation, panel_height, instanceId) {
        super(orientation, panel_height, instanceId);

        this.setAllowedLayout(Applet.AllowedLayout.BOTH);

        this.metadata = metadata;
        this.settings = new Settings.AppletSettings(this, metadata.uuid, instanceId);
        this.settings.bind("showtrack", "showtrack", this.on_settings_changed);
        this.settings.bind("middleClickAction", "middleClickAction");
        this.settings.bind("middleShiftClickAction", "middleShiftClickAction");
        this.settings.bind("horizontalScroll", "horizontalScroll")
        this.settings.bind("showalbum", "showalbum", this.on_settings_changed);
        this.settings.bind("truncatetext", "truncatetext", this.on_settings_changed);
        this.settings.bind("hideSystray", "hideSystray", function() {
            if (this.hideSystray) this.registerSystrayIcons();
            else this.unregisterSystrayIcons();
        });

        this.settings.bind("playerControl", "playerControl", this.on_settings_changed);
        this.settings.bind("extendedPlayerControl", "extendedPlayerControl", function() {
            for(let i in this._players)
                this._players[i].onSettingsChanged();
        });

        this.settings.bind("_knownPlayers", "_knownPlayers");
        if (this.hideSystray) this.registerSystrayIcons();

        this.settings.bind("keyOpen", "keyOpen", this._setKeybinding);
        this.settings.bind("alwaysShowMuteInput", "alwaysShowMuteInput", this.on_settings_changed);

        this.settings.bind("tooltipShowVolume", "tooltipShowVolume", this.on_settings_changed);
        this.settings.bind("tooltipShowPlayer", "tooltipShowPlayer", this.on_settings_changed);
        this.settings.bind("tooltipShowArtistTitle", "tooltipShowArtistTitle", this.on_settings_changed);

        // FX-rack theme: palette is global (module constructors read T at build
        // time), so a theme change rebuilds the mixer section in place.
        RACK_DIR = metadata.path;
        this.settings.bind("rackTheme", "rackTheme", function() {
            _applyRackTheme(this.rackTheme);
        });
        _applyRackTheme(this.rackTheme);
        
        this.settings.bind("rackLogoBadge", "rackLogoBadge", function() {
            RACK_LOGO_BADGE = !!this.rackLogoBadge;
            Mainloop.timeout_add(500, () => {
                Util.spawnCommandLine("dbus-send --session --dest=org.Cinnamon.LookingGlass --type=method_call /org/Cinnamon/LookingGlass org.Cinnamon.LookingGlass.ReloadExtension string:'sound@cinnamon.org' string:'APPLET'");
            });
        });
        RACK_LOGO_BADGE = !!this.rackLogoBadge;

        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.menuManager.addMenu(this.menu);
        this._setKeybinding();

        this.set_applet_icon_symbolic_name('xsi-audio-x-generic');

        this._players = {};
        this._playerItems = [];
        this._activePlayer = null;

        Interfaces.getDBusAsync((proxy, error) => {
            if (error) {
                // ?? what else should we do if we fail completely here?
                throw error;
            }

            this._dbus = proxy;

            // player DBus name pattern
            let name_regex = /^org\.mpris\.MediaPlayer2\./;
            // load players
            this._dbus.ListNamesRemote((names) => {
                for (let n in names[0]) {
                    let name = names[0][n];
                    if (name_regex.test(name))
                        this._dbus.GetNameOwnerRemote(name, (owner) => this._addPlayer(name, owner[0]));
                }
            });

            // watch players
            this._ownerChangedId = this._dbus.connectSignal('NameOwnerChanged',
                (proxy, sender, [name, old_owner, new_owner]) => {
                    if (name_regex.test(name)) {
                        if (new_owner && !old_owner)
                            this._addPlayer(name, new_owner);
                        else if (old_owner && !new_owner)
                            this._removePlayer(name, old_owner);
                        else
                            this._changePlayerOwner(name, old_owner, new_owner);
                    }
                }
            );
        });

        this._control = new Cvc.MixerControl({ name: 'Cinnamon Volume Control' });
        this._control.connect('state-changed', (...args) => this._onControlStateChanged(...args));

        this._control.connect('output-added', (...args) => this._onDeviceAdded(...args, "output"));
        this._control.connect('output-removed', (...args) => this._onDeviceRemoved(...args, "output"));
        this._control.connect('active-output-update', (...args) => this._onDeviceUpdate(...args, "output"));

        this._control.connect('input-added', (...args) => this._onDeviceAdded(...args, "input"));
        this._control.connect('input-removed', (...args) => this._onDeviceRemoved(...args, "input"));
        this._control.connect('active-input-update', (...args) => this._onDeviceUpdate(...args, "input"));

        this._control.connect('stream-added', (...args) => this._onStreamAdded(...args));
        this._control.connect('stream-removed', (...args) => this._onStreamRemoved(...args));

        this._sound_settings = new Gio.Settings({ schema_id: CINNAMON_DESKTOP_SOUNDS });
        this._volumeNorm = this._control.get_vol_max_norm();
        this._volumeMax = this._volumeNorm;

        this._streams = [];
        this._devices = [];
        this._recordingAppsNum = 0;

        this._output = null;
        this._outputMutedId = 0;
        this._outputIcon = "xsi-audio-volume-muted";

        this._input = null;
        this._inputMutedId = 0;

        this._icon_name = '';
        this._icon_path = null;
        this._iconTimeoutId = 0;

        this.actor.connect('scroll-event', (...args) => this._onScrollEvent(...args));

        this.mute_out_switch = new PopupMenu.PopupSwitchIconMenuItem(_("Mute output"), false, "xsi-audio-volume-muted", St.IconType.SYMBOLIC);
        this.mute_in_switch = new PopupMenu.PopupSwitchIconMenuItem(_("Mute input"), false, "xsi-microphone-sensitivity-muted", St.IconType.SYMBOLIC);
        this._applet_context_menu.addMenuItem(this.mute_out_switch);
        this._applet_context_menu.addMenuItem(this.mute_in_switch);
        if (this.alwaysShowMuteInput)
            this.mute_in_switch.actor.show();
        else
            this.mute_in_switch.actor.hide();

        this._applet_context_menu.addAction(_("Equalizer"), () => {
            Util.spawn(['/home/lumba/.local/bin/pipewire-eq-gui']);
        });
        
        this._contextThemeMenu = new PopupMenu.PopupSubMenuMenuItem(_("🎨 Studio FX Theme"));
        for (let key in RACK_THEMES) {
            let displayName = key.toUpperCase();
            let item = new PopupMenu.PopupMenuItem(displayName);
            if (this.rackTheme === key) {
                item.label.set_style("font-weight: bold; color: #fbbf24;");
            }
            item.connect('activate', () => {
                global.log("FOVEAI: Theme clicked! " + key);
                let stamp = Date.now().toString();
                Util.spawnCommandLine("sh -c 'echo " + stamp + " > /tmp/foveai_sound_menu_open'");
                this.settings.setValue('rackTheme', key);
                Mainloop.timeout_add(500, () => {
                    global.log("FOVEAI: Firing global.reexec_self() for " + key);
                    Util.spawnCommandLine("dbus-send --type=method_call --dest=org.Cinnamon /org/Cinnamon org.Cinnamon.Eval string:'global.reexec_self()'");
                    return false;
                });
            });
            this._contextThemeMenu.menu.addMenuItem(item);
        }
        this._applet_context_menu.addMenuItem(this._contextThemeMenu);

        this._applet_context_menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._outputApplicationsMenu = new PopupMenu.PopupSubMenuMenuItem(_("Applications"));
        this._selectOutputDeviceItem = new PopupMenu.PopupSubMenuMenuItem(_("Output device"));
        this._applet_context_menu.addMenuItem(this._outputApplicationsMenu);
        this._applet_context_menu.addMenuItem(this._selectOutputDeviceItem);
        this._outputApplicationsMenu.actor.hide();
        this._selectOutputDeviceItem.actor.hide();

        this._inputSection = new PopupMenu.PopupMenuSection();
        this._inputVolumeSection = new VolumeSlider(this, null, _("Microphone"), null);
        this._inputVolumeSection.connect("values-changed", (...args) => this._inputValuesChanged(...args));
        this._selectInputDeviceItem = new PopupMenu.PopupSubMenuMenuItem(_("Input device"));
        this._inputSection.addMenuItem(this._inputVolumeSection);
        this._inputSection.addMenuItem(this._selectInputDeviceItem);
        this._applet_context_menu.addMenuItem(this._inputSection);

        this._selectInputDeviceItem.actor.hide();
        this._inputSection.actor.hide();

        this._applet_context_menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this.mute_out_switch.connect('toggled', () => this._toggle_out_mute());
        this.mute_in_switch.connect('toggled', () => this._toggle_in_mute());

        this._control.open();

        this._volumeControlShown = false;

        this._showFixedElements();
        this.set_show_label_in_vertical_panels(false);
        this.set_applet_label(this._applet_label.get_text());

        try {
            let popupFile = Gio.File.new_for_path("/tmp/foveai_sound_menu_open");
            if (popupFile.query_exists(null)) {
                let [success, content] = popupFile.load_contents(null);
                if (success) {
                    let stamp = parseInt(content.toString().trim(), 10);
                    if (!isNaN(stamp) && (Date.now() - stamp) < 15000) {
                        Mainloop.timeout_add(1500, () => {
                            if (this.menu && !this.menu.isOpen) {
                                this.menu.open(true);
                            }
                            return false;
                        });
                    }
                }
                popupFile.delete(null);
            }
        } catch(e) {
            global.log("Error handling menu popup file: " + e);
        }

        let appsys = Cinnamon.AppSystem.get_default();
        appsys.connect("installed-changed", () => this._updateLaunchPlayer());

        this._sound_settings.connect("changed::" + OVERAMPLIFICATION_KEY, () => this._on_overamplification_change());
        this._on_overamplification_change();
    }

    _setKeybinding() {
        Main.keybindingManager.addXletHotKey(this, "sound-open", this.keyOpen, Lang.bind(this, this._openMenu));
    }

    _on_overamplification_change () {
        if (this._sound_settings.get_boolean(OVERAMPLIFICATION_KEY)) {
            this._volumeMax = 1.5 * this._volumeNorm;
            this._outputVolumeSection.set_mark(1/1.5);
            if (this._inputVolumeMain) this._inputVolumeMain.set_mark(1/1.5);
        }
        else {
            this._volumeMax = this._volumeNorm;
            this._outputVolumeSection.set_mark(0);
            if (this._inputVolumeMain) this._inputVolumeMain.set_mark(0);
        }
        this._outputVolumeSection._update();
    }

    on_settings_changed () {
        if(this.playerControl && this._activePlayer)
            this.setAppletTextIcon(this._players[this._activePlayer], true);
        else
            this.setAppletTextIcon();

        if (this.alwaysShowMuteInput)
            this.mute_in_switch.actor.show();
        else if (this._recordingAppsNum === 0)
            this.mute_in_switch.actor.hide();

        this._changeActivePlayer(this._activePlayer);
    }

    on_applet_removed_from_panel () {
        Main.keybindingManager.removeXletHotKey(this, "sound-open");
        if (this.hideSystray)
            this.unregisterSystrayIcons();
        if (this._iconTimeoutId) {
            Mainloop.source_remove(this._iconTimeoutId);
            this._iconTimeoutId = 0;
        }

        this._dbus.disconnectSignal(this._ownerChangedId);

        for(let i in this._players)
            this._players[i].destroy();

        if (this._control)
            this._control.close();
    }

    on_applet_clicked(event) {
        this._openMenu();
    }

    _openMenu() {
        this.menu.toggle();
    }

    _toggle_out_mute() {
        if (!this._output)
            return;

        if (this._output.is_muted) {
            this._output.change_is_muted(false);
            this.mute_out_switch.setToggleState(false);
        } else {
            this._output.change_is_muted(true);
            this.mute_out_switch.setToggleState(true);
        }
    }

    _toggle_in_mute() {
        if (!this._input)
            return;

        let newStatus = !this._input.is_muted;
        this._input.change_is_muted(newStatus);
        this.mute_in_switch.setToggleState(newStatus);
    }

    _onScrollEvent(actor, event) {
        const direction = event.get_scroll_direction();

        if (direction == Clutter.ScrollDirection.SMOOTH) {
            return Clutter.EVENT_PROPAGATE;
        }

        let currentVolume = this._output.volume;
        let volumeChange = false;
        let player = this._players[this._activePlayer];

        if (direction == Clutter.ScrollDirection.DOWN) {
            let prev_muted = this._output.is_muted;
            this._output.volume = Math.max(0, currentVolume - this._volumeNorm * VOLUME_ADJUSTMENT_STEP);
            if (this._output.volume < 1) {
                this._output.volume = 0;
                if (!prev_muted)
                    this._output.change_is_muted(true);
            } else {
                // 100% is magnetic:
                if (this._output.volume!=this._volumeNorm && this._output.volume>this._volumeNorm*(1-VOLUME_ADJUSTMENT_STEP/2) && this._output.volume<this._volumeNorm*(1+VOLUME_ADJUSTMENT_STEP/2))
                    this._output.volume=this._volumeNorm;
            }

            volumeChange = true;
        }
        else if (direction == Clutter.ScrollDirection.UP) {
            this._output.volume = Math.min(this._volumeMax, currentVolume + this._volumeNorm * VOLUME_ADJUSTMENT_STEP);
            // 100% is magnetic:
            if (this._output.volume!=this._volumeNorm && this._output.volume>this._volumeNorm*(1-VOLUME_ADJUSTMENT_STEP/2) && this._output.volume<this._volumeNorm*(1+VOLUME_ADJUSTMENT_STEP/2))
                this._output.volume=this._volumeNorm;

            this._output.change_is_muted(false);
            volumeChange = true;
        }
        else if (this.horizontalScroll && player !== null && player._playerStatus !== "Stopped") {
            if (direction == Clutter.ScrollDirection.LEFT) {
                this._players[this._activePlayer]._mediaServerPlayer.PreviousRemote();
            }
            else if (direction == Clutter.ScrollDirection.RIGHT) {
                this._players[this._activePlayer]._mediaServerPlayer.NextRemote();
            }
        }

        if (volumeChange) {
            this._output.push_volume();
            this._notifyVolumeChange(this._output);
            this._applet_tooltip.show();
        } else {
            this._applet_tooltip.hide();
        }
    }

    _onButtonPressEvent (actor, event) {
        let buttonId = event.get_button();
        let modifiers = Cinnamon.get_event_state(event);
        let shiftPressed = (modifiers & Clutter.ModifierType.SHIFT_MASK);

        //mute or play / pause players on middle click
        if (buttonId === 2) {
            if (shiftPressed) {
                if (this.middleShiftClickAction === "mute") {
                    if (this._input && this._output && this._output.is_muted === this._input.is_muted)
                        this._toggle_in_mute();
                    this._toggle_out_mute();
                } else if (this.middleShiftClickAction === "out_mute")
                    this._toggle_out_mute();
                else if (this.middleShiftClickAction === "in_mute")
                    this._toggle_in_mute();
                else if (this.middleShiftClickAction === "player")
                    this._players[this._activePlayer]._mediaServerPlayer.PlayPauseRemote();
            } else {
                if (this.middleClickAction === "mute") {
                    if (this._input && this._output && this._output.is_muted === this._input.is_muted)
                        this._toggle_in_mute();
                    this._toggle_out_mute();
                } else if (this.middleClickAction === "out_mute")
                    this._toggle_out_mute();
                else if (this.middleClickAction === "in_mute")
                    this._toggle_in_mute();
                else if (this.middleClickAction === "player")
                    this._players[this._activePlayer]._mediaServerPlayer.PlayPauseRemote();
            }
        } else if (buttonId === 8) { // previous and next track on mouse buttons 4 and 5 (8 and 9 by X11 numbering)
            this._players[this._activePlayer]._mediaServerPlayer.PreviousRemote();
        } else if (buttonId === 9) {
            this._players[this._activePlayer]._mediaServerPlayer.NextRemote();
        } else {
            return Applet.Applet.prototype._onButtonPressEvent.call(this, actor, event);
        }
        return Clutter.EVENT_STOP;
    }

    setIcon(icon, source) {
        if (this._iconTimeoutId) {
            Mainloop.source_remove(this._iconTimeoutId);
            this._iconTimeoutId = 0;
        }

        //save the icon
        if (source) {
            if (source === "output")
                this._outputIcon = icon;
            else
                this._playerIcon = [icon, source === "player-path"];
        }

        if (this.playerControl && this._activePlayer && this._playerIcon[0]) {
            if (source === "output") {
                // if we have an active player, but are changing the volume, show the output icon and after three seconds change back to the player icon unless muted
                this.set_applet_icon_symbolic_name(this._outputIcon);
                if (this._output && !this._output.is_muted) {
                    this._iconTimeoutId = Mainloop.timeout_add_seconds(OUTPUT_ICON_SHOW_TIME_SECONDS, () => {
                        this.setIcon();
                    });
                }
            } else {
                // if we have an active player and want to change the icon, change it immediately
                if (this._playerIcon[1])
                    this.set_applet_icon_path(this._playerIcon[0]);
                else
                    this.set_applet_icon_symbolic_name(this._playerIcon[0]);
            }
        } else {
            //if we have no active player show the output icon
            this.set_applet_icon_symbolic_name(this._outputIcon);
        }
    }

    setAppletIcon(player, path) {
        if (path) {
            if (path === true) {
                // Restore the icon path from the saved path.
                path = this._icon_path;
            } else {
                this._icon_path = path;
            }
        } else if (path === null) {
            // This track has no art, erase the saved path.
            this._icon_path = null;
        }

        if (player && (player === true || player._playerStatus == 'Playing')) {
            // Something is playing
            if (this.showalbum) {
                if (path) {
                    this.setIcon(path, "player-path");
                } else {
                    this.setIcon('xsi-media-optical-cd-audio', 'player-name');
                }
            } else {
                this.setIcon('xsi-audio-x-generic', 'player-name');
            }
        } else {
            // Nothing is playing - clear player icon and show volume icon
            this._playerIcon = [null, false];
            this.setIcon(this._outputIcon);
        }
    }

    setAppletText(player) {
        let title_text = "";
        if (this.showtrack && player && player._playerStatus == 'Playing') {
            if (player._artist == "Unknown Artist") {
                title_text = player._title;
            }
            else {
                title_text = player._title + ' - ' + player._artist;
            }
            const glyphs = Util.splitByGlyph(title_text);
            if (glyphs.length > this.truncatetext) {
                title_text = glyphs.slice(0, this.truncatetext - 3).join("") + "...";
            }
        }
        this.set_applet_label(title_text);
    }

    setAppletTextIcon(player, icon) {
        this.player = player;
        if (player && player._owner != this._activePlayer)
            return;
        this.setAppletIcon(player, icon);
        this.setAppletText(player);
        this.setAppletTooltip();
    }

    setAppletTooltip() {
        let tooltips = [];
        if (this.tooltipShowVolume) {
            tooltips.push(_("Volume") + ": " + this.volume);
            if (this.micVolume)
                tooltips.push(_("Microphone") + ": " + this.micVolume);
        }
        if (this.player && this.player._owner == this._activePlayer) {
            if (this.tooltipShowPlayer) {
                tooltips.push(this.player._name + " - " + _(this.player._playerStatus));
            }
            if (this.tooltipShowArtistTitle) {
                if (this.player._artist != _("Unknown Artist")) {
                    tooltips.push(this.player._artist);
                }
                if (this._title != _("Unknown Title")) {
                    tooltips.push(this.player._title);
                }
            }
        }
        this.set_applet_tooltip(tooltips.join("\n"));
    }

    _isInstance(busName) {
        // MPRIS instances are in the form
        //   org.mpris.MediaPlayer2.name.instanceXXXX
        // ...except for VLC, which to this day uses
        //   org.mpris.MediaPlayer2.name-XXXX
        return busName.split('.').length > 4 ||
                /^org\.mpris\.MediaPlayer2\.vlc-\d+$/.test(busName);
    }

    _addPlayer(busName, owner) {
        if (this._players[owner]) {
            let prevName = this._players[owner]._busName;
            // HAVE: ADDING: ACTION:
            // master master reject, cannot happen
            // master instance upgrade to instance
            // instance master reject, duplicate
            // instance instance reject, cannot happen
            if (this._isInstance(busName) && !this._isInstance(prevName))
                this._players[owner]._busName = busName;
            else
                return;
        } else if (owner) {
            let player = new Player(this, busName, owner);

            // Add the player to the list of active players in GUI.
            // We don't have the org.mpris.MediaPlayer2 interface set up at this point,
            // add the player's busName as a placeholder until we can get its Identity.
            let item = new PopupMenu.PopupMenuItem(busName);
            item.activate = () => this._switchPlayer(player._owner);
            this._chooseActivePlayerItem.menu.addMenuItem(item);

            this._players[owner] = player;
            this._playerItems.push({ player: player, item: item });

            this._changeActivePlayer(owner);
            this._updatePlayerMenuItems();
            this.setAppletTextIcon(this._players[this._activePlayer], true);
        }
    }

    _switchPlayer(owner) {
        if(this._players[owner]) {
            // The player exists, switch to it
            this._changeActivePlayer(owner);
            this._updatePlayerMenuItems();
            this.setAppletTextIcon(this._players[this._activePlayer], true);
        } else {
            // The player doesn't seem to exist. Remove it from the players list
            this._removePlayerItem(owner);
            this._updatePlayerMenuItems();
        }
    }

    _removePlayerItem(owner) {
        // Remove the player from the player switching list
        for(let i = 0, l = this._playerItems.length; i < l; ++i) {
            let playerItem = this._playerItems[i];
            if(playerItem.player._owner === owner) {
                playerItem.item.destroy();
                this._playerItems.splice(i, 1);
                break;
            }
        }
    }

    _removePlayer(busName, owner) {
        if (this._players[owner] && this._players[owner]._busName == busName) {
            this._removePlayerItem(owner);

            this._players[owner].destroy();
            delete this._players[owner];

            if (this._activePlayer == owner) {
                //set _activePlayer to null if we have none now, or to the first value in the players list
                this._activePlayer = null;
                for (let i in this._players) {
                    this._changeActivePlayer(i);
                    break;
                }
            }
            this._updatePlayerMenuItems();
            this.setAppletTextIcon(this._players[this._activePlayer], true);
        }
    }

    _changePlayerOwner(busName, oldOwner, newOwner) {
        if (this._players[oldOwner] && busName == this._players[oldOwner]._busName) {
            this._players[newOwner] = this._players[oldOwner];
            this._players[newOwner]._owner = newOwner;
            delete this._players[oldOwner];
            if (this._activePlayer == oldOwner)
                this._activePlayer = newOwner;
        }
    }

    //will be called by an instance of #Player
    passDesktopEntry(entry) {
        //do we know already this player?
        for (let i = 0, l = this._knownPlayers.length; i < l; ++i) {
            if (this._knownPlayers[i] === entry)
                return;
        }
        //No, save it to _knownPlayers and update player list
        this._knownPlayers.push(entry);
        this._knownPlayers.save();
        this._updateLaunchPlayer();
    }

    _showFixedElements() {
        // The launch player list
        this._launchPlayerItem = new PopupMenu.PopupSubMenuMenuItem(_("Launch player"));
        this.menu.addMenuItem(this._launchPlayerItem);
        this._updateLaunchPlayer();

        // The list to use when switching between active players
        this._chooseActivePlayerItem = new PopupMenu.PopupSubMenuMenuItem(_("Choose player controls"));
        this._chooseActivePlayerItem.actor.hide();
        this.menu.addMenuItem(this._chooseActivePlayerItem);

        //between these two separators will be the player MenuSection (position 3)
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this._outputVolumeSection = new VolumeSlider(this, null, _("Volume"), null);
        this._outputVolumeSection.connect("values-changed", (...args) => this._outputValuesChanged(...args));

        this._inputVolumeMain = new VolumeSlider(this, null, _("Microphone"), null);
        this._inputVolumeMain.set_mark(this._volumeMax > this._volumeNorm ? 1/1.5 : 0);
        this._inputVolumeMain.connect("values-changed", (...args) => this._inputValuesChanged(...args));

        // --- Two-column studio mixer: OUTPUT left / INPUT right ---
        this._mixerSection = new StudioMixerSection(this._outputVolumeSection, this._inputVolumeMain, this);
        this.menu.addMenuItem(this._mixerSection);
        this._mixerSection._menuInsertIndex = this.menu._getMenuItems().indexOf(this._mixerSection);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this.menu.addAction(_("Open Full EQ Window"), () => {
            Util.spawn(['/home/lumba/.local/bin/pipewire-eq-gui']);
        });
        this.menu.addSettingsAction(_("Sound Settings"), 'sound');
    }

    // Rebuild the FX rack in place after a theme/logo setting change.
    _rebuildMixer() {
        if (!this._mixerSection || !this.menu) return;
        let idx = this._mixerSection._menuInsertIndex;
        if (idx === undefined || idx < 0)
            idx = this.menu._getMenuItems().indexOf(this._mixerSection);
        this._mixerSection.destroy();
        this._mixerSection = new StudioMixerSection(this._outputVolumeSection, this._inputVolumeMain, this);
        this.menu.addMenuItem(this._mixerSection, idx >= 0 ? idx : undefined);
        this._mixerSection._menuInsertIndex = idx;
    }

    _updateLaunchPlayer() {
        let availablePlayers = [];

        let appsys = Cinnamon.AppSystem.get_default();
        //_knownPlayers is an array containing the paths of desktop files
        for(let i = 0, l = this._knownPlayers.length; i < l; ++i) {
            let app = appsys.lookup_app(this._knownPlayers[i] + ".desktop");
            if (app)
                availablePlayers.push(app);
        }

        this._launchPlayerItem.menu.removeAll();

        if (availablePlayers.length > 0) {
            for (var p = 0; p < availablePlayers.length; p++) {
                let playerApp = availablePlayers[p];
                let menuItem = new MediaPlayerLauncher(playerApp, this._launchPlayerItem.menu);
                this._launchPlayerItem.menu.addMenuItem(menuItem);
            }
        }

        if (!this.playerControl || !availablePlayers.length) {
            this._launchPlayerItem.actor.hide();
        }
    }

    _updatePlayerMenuItems() {
        if (this.playerControl && this._activePlayer) {
            this._launchPlayerItem.actor.show();
            this._chooseActivePlayerItem.actor.show();

            // Show a dot on the active player in the switching menu
            for (let i = 0, l = this._playerItems.length; i < l; ++i) {
                let playerItem = this._playerItems[i];

                playerItem.item.setLabel(playerItem.player._name);
                playerItem.item.setShowDot(playerItem.player._owner === this._activePlayer);
            }

            // Hide the switching menu if we only have at most one active player
            if(this._chooseActivePlayerItem.menu.numMenuItems <= 1) {
                this._chooseActivePlayerItem.actor.hide();
            }
        } else {
            if (this.playerControl && this._launchPlayerItem.menu.numMenuItems) {
                this._launchPlayerItem.actor.show();
            } else {
                this._launchPlayerItem.actor.hide();
                this._chooseActivePlayerItem.actor.hide();
            }
        }
    }

    _changeActivePlayer(player) {
        if (this._activePlayer)
            this.menu.box.remove_actor(this._players[this._activePlayer].actor);

        this._activePlayer = player;
        if (this.playerControl && this._activePlayer != null) {
            let menuItem = this._players[player];
            this.menu.addMenuItem(menuItem, 2);
            this._icon_path = menuItem._cover_path || null;
        } else {
            this._icon_path = null;
        }

        this._updatePlayerMenuItems();
    }

    _notifyVolumeChange(stream) {
        Main.soundManager.play('volume');
    }

    _mutedChanged(object, param_spec, property) {
        if (property == "_output") {
            this.mute_out_switch.setToggleState(this._output.is_muted);
        } else if (property == "_input") {
            this.mute_in_switch.setToggleState(this._input.is_muted);
        }
    }

    _outputValuesChanged(actor, iconName, percentage) {
        this.setIcon(iconName, "output");
        this.mute_out_switch.setIconSymbolicName(iconName);
        this.volume = percentage;
        this.setAppletTooltip();
    }

    _inputValuesChanged(actor, iconName, percentage) {
        this.mute_in_switch.setIconSymbolicName(iconName);
        this.micVolume = percentage;
        this.setAppletTooltip();
    }

    _onControlStateChanged() {
        if (this._control.get_state() == Cvc.MixerControlState.READY) {
            this._readOutput();
            this._readInput();
            this.actor.show();
        } else {
            this.actor.hide();
        }
    }

    _readOutput() {
        if (this._outputMutedId) {
            this._output.disconnect(this._outputMutedId);
            this._outputMutedId = 0;
        }
        this._output = this._control.get_default_sink();
        if (this._output) {
            this._outputVolumeSection.connectWithStream(this._output);
            this._outputMutedId = this._output.connect('notify::is-muted', (...args) => this._mutedChanged(...args, '_output'));
            this._mutedChanged (null, null, '_output');
        } else {
            this.setIcon("xsi-audio-volume-muted-symbolic", "output");
        }
    }

    _readInput() {
        if (this._inputMutedId) {
            this._input.disconnect(this._inputMutedId);
            this._inputMutedId = 0;
        }
        this._input = this._control.get_default_source();
        if (this._input) {
            this._inputVolumeSection.connectWithStream(this._input);
            if (this._inputVolumeMain)
                this._inputVolumeMain.connectWithStream(this._input);
            this._inputMutedId = this._input.connect('notify::is-muted', (...args) => this._mutedChanged(...args, '_input'));
            this._mutedChanged (null, null, '_input');
        } else {
            this._inputSection.actor.hide();
        }
    }

    _onDeviceAdded(control, id, type) {
        let device = this._control["lookup_" + type + "_id"](id);

        let item = new PopupMenu.PopupMenuItem(device.description);
        item.activate = () => this._control["change_" + type](device);

        let bin = new St.Bin({ x_align: St.Align.END, style_class: 'popup-inactive-menu-item' });
        let label = new St.Label({ text: device.origin });
        bin.add_actor(label);
        item.addActor(bin, { expand: true, span: -1, align: St.Align.END });

        let selectItem = this["_select" + type[0].toUpperCase() + type.slice(1) + "DeviceItem"];
        selectItem.menu.addMenuItem(item);
        //show the menu if we have more than two devices
        if(selectItem.menu.numMenuItems > 1)
            selectItem.actor.show();

        this._devices.push({id: id, type: type, item: item});
    }

    _onDeviceRemoved(control, id, type) {
        for (let i = 0, l = this._devices.length; i < l; ++i) {
            if (this._devices[i].type === type && this._devices[i].id === id) {
                let device = this._devices[i];
                if (device.item)
                    device.item.destroy();

                //hide submenu if showing them is unnecessary
                let selectItem = this["_select" + type[0].toUpperCase() + type.slice(1) + "DeviceItem"];
                if (selectItem.menu.numMenuItems <= 1)
                    selectItem.actor.hide();

                this._devices.splice(i, 1);
                break;
            }
        }
    }

    _onDeviceUpdate(control, id, type) {
        this["_read" + type[0].toUpperCase() + type.slice(1)]();

        for (let i = 0, l = this._devices.length; i < l; ++i) {
            if (this._devices[i].type === type)
                this._devices[i].item.setShowDot(id === this._devices[i].id);
        }
    }

    _onStreamAdded(control, id) {
        let stream = this._control.lookup_stream_id(id);
        let appId = stream.application_id;

        if (stream.is_virtual || appId === "org.freedesktop.libcanberra") {
            //sort out unwanted streams
            return;
        }

        if (stream instanceof Cvc.MixerSinkInput) {
            //for sink inputs, add a menuitem to the application submenu
            let item = new StreamMenuSection(this, stream);
            this._outputApplicationsMenu.menu.addMenuItem(item);
            this._outputApplicationsMenu.actor.show();
            this._streams.push({id: id, type: "SinkInput", item: item});
        } else if (stream instanceof Cvc.MixerSourceOutput) {
            //for source outputs, only show the input section
            this._streams.push({id: id, type: "SourceOutput"});
            if (this._recordingAppsNum++ === 0) {
                this._inputSection.actor.show();
                this.mute_in_switch.actor.show();
            }
        }
    }

    _onStreamRemoved(control, id) {
        for (let i = 0, l = this._streams.length; i < l; ++i) {
            if(this._streams[i].id === id) {
                let stream = this._streams[i];
                if(stream.item)
                    stream.item.destroy();

                //hide submenus or sections if showing them is unnecessary
                if (stream.type === "SinkInput") {
                    if (this._outputApplicationsMenu.menu.numMenuItems === 0)
                        this._outputApplicationsMenu.actor.hide();
                } else if (stream.type === "SourceOutput") {
                    if(--this._recordingAppsNum === 0) {
                        this._inputSection.actor.hide();
                        this.mute_in_switch.actor.hide();
                    }
                    if (this.alwaysShowMuteInput)
                        this.mute_in_switch.actor.show();
                }
                this._streams.splice(i, 1);
                break;
            }
        }
    }

    registerSystrayIcons() {
        for (let i = 0; i < players_with_seek_support.length; i++) {
            Main.systrayManager.registerTrayIconReplacement(players_with_seek_support[i], this.metadata.uuid);
        }
        for (let i = 0; i < players_without_seek_support.length; i++) {
            Main.systrayManager.registerTrayIconReplacement(players_without_seek_support[i], this.metadata.uuid);
        }
    }

    unregisterSystrayIcons() {
        Main.systrayManager.unregisterTrayIconReplacement(this.metadata.uuid);
    }
}

function main(metadata, orientation, panel_height, instanceId) {
    return new CinnamonSoundApplet(metadata, orientation, panel_height, instanceId);
}
