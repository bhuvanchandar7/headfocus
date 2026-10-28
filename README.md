# HeadFocus

**Turn your head toward a monitor, and the window on it becomes active. Just start typing.**

For macOS with two or more displays. HeadFocus watches your head direction through the
webcam and, when you turn to face a different display, activates the top window on it.
No clicking, no moving the mouse. The cursor is left alone.

- Runs fully on your Mac. No video is saved or sent anywhere.
- Ignores quick glances and turns away from your screens (phone, people in the room).
- Leaves you alone otherwise: Cmd+Tab and clicking work as usual.
- Easy to switch off: click the eye in the menu bar, or press **⌃⌥⌘H** (Control+Option+Command+H).

## Install

You need macOS, two or more displays, a webcam, and Xcode Command Line Tools
(`xcode-select --install` if you don't have them).

```bash
git clone https://github.com/bhuvanchandar7/headfocus.git
cd headfocus
./setup.sh
```

`setup.sh` creates a Python environment, downloads MediaPipe's face model (about 4 MB),
and builds a small `HeadFocus.app` in `~/Applications`. If [uv](https://docs.astral.sh/uv/)
is installed it is used; otherwise you need Python 3.10 to 3.12 (`brew install python@3.12`).

## Use

Run these **in the Terminal app**. macOS gives camera access per app, so Terminal needs to
be the one asking.

**1. Calibrate.** Turn your head to face each display when asked and press Enter.
Allow camera access for Terminal if macOS asks, then run it again.
```bash
./headfocus calibrate
```
Turn your whole head, not just your eyes. If it warns that displays are too close
together, calibrate again with bigger turns.

**2. Try it.** The preview window shows the camera with your head angles.
Press Ctrl+C to stop.
```bash
./headfocus run --preview
```
macOS will ask for **Accessibility** permission (needed to switch windows).
Turn it on for Terminal in System Settings > Privacy & Security > Accessibility, then run again.

**3. Run it in the background at every login.**
```bash
./headfocus install
```
macOS treats HeadFocus as its own app, so it asks once more for **Camera** and
**Accessibility** for "HeadFocus". The settings page opens for you. After you allow
both, it starts within 30 seconds.

## Turning it on and off

- **Menu bar:** click the eye icon and choose **Turn Off** / **Turn On**. The icon shows an eye
  when on and a crossed-out eye when off. The menu also shows which display you're facing,
  and has Recalibrate, Show Log, and Quit.
- **Keyboard:** press **⌃⌥⌘H** anywhere to toggle. You'll hear a short sound.
- **Terminal:** `./headfocus on`, `./headfocus off`, or `./headfocus toggle`.

When off, the camera is released, so the webcam light goes out. It stays off (even after
a restart) until you turn it back on. **Quit** from the menu stops it until your next login;
`./headfocus on` starts it again.

To use a different shortcut, add for example `"hotkey": "ctrl+opt+h"` to `config.json`
and run `./headfocus restart`. Modifiers: `ctrl`, `opt`, `cmd`, `shift`.

## Commands

| Command | What it does |
|---|---|
| `./headfocus status` | Is the background copy running? |
| `./headfocus log` | Watch which display it thinks you're facing |
| `./headfocus on` / `off` / `toggle` | Turn tracking on or off (off releases the camera) |
| `./headfocus stop` / `start` | Stop the background copy until next login / start it |
| `./headfocus calibrate` | Recalibrate (after moving your chair, laptop, or camera) |
| `./headfocus uninstall` | Stop running at login |
| `./headfocus displays` | List displays and the top window on each |
| `./headfocus focus 1` | Focus the top window on display 1 (no camera, for testing) |

## Tuning

Add any of these to `config.json` (created by calibration), then `./headfocus restart`:

| Key | Default | Raise it if... |
|---|---|---|
| `"dwell"` | `0.3` | quick glances switch windows (seconds you must face a display) |
| `"margin"` | `3.0` | it flips back and forth between displays (degrees) |
| `"max_dist"` | `22.0` | turning slightly past a display doesn't count as facing it (degrees) |
| `"hotkey"` | `"ctrl+opt+cmd+h"` | another app uses the same shortcut |
| `"debug"` | `false` | set `true` to log your head angle twice a second |

When running in the foreground you can also pass `--dwell`, `--margin`, `--camera N`
(pick another camera), `--move-cursor` (also move the mouse to the focused window)
and `--no-menubar`.

## How it works

1. [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)
   estimates your head's yaw and pitch from the webcam, about 15 times a second.
2. Calibration records the angle at which you face each display. While running, you're
   "facing" whichever calibrated angle is closest, as long as you hold it for `dwell` seconds
   and it's clearly closer than the current one (`margin`).
3. When that changes, HeadFocus finds the frontmost window on the new display and raises
   it with the macOS Accessibility API. The app restores the last text box you used, so
   you can type right away.

`HeadFocus.app` is a tiny launcher (`launcher/main.c`) that runs `headfocus.py`.
It exists so macOS can grant camera and Accessibility permission to a named app
instead of to Python itself.

## Limitations

- It tracks your head, not your eyes. Glancing at another screen with only your eyes won't switch.
- The webcam light stays on while it's on. Turn it off when you don't need it.
- It activates the window. Which text box gets the cursor is up to the app (most restore the last one).
- Recalibrate if you rearrange your displays or move the camera.
- If you move this folder, run `./setup.sh` and `./headfocus install` again.

## Uninstall

```bash
./headfocus uninstall
rm -rf ~/Applications/HeadFocus.app
```
Then delete this folder and remove HeadFocus from System Settings > Privacy & Security
> Camera and Accessibility.

## License

MIT
