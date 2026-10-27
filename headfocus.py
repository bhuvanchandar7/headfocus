#!/usr/bin/env python3
"""Head-turn display focus for macOS.

Watches your head direction through the webcam. When you turn to face a
different display and hold it briefly, the top window on that display becomes
the active window, so you can type into it right away.

Commands:
  calibrate          look at each display when asked; saves config.json
  run [--preview]    start tracking (Ctrl+C to stop)
  displays           list displays and the top window on each
  focus N            focus the top window on display N (no camera, for testing)
"""

import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")
MODEL = os.path.join(HERE, "models", "face_landmarker.task")

IGNORED_OWNERS = {
    "Window Server", "Dock", "Control Center", "Notification Center",
    "SystemUIServer", "Spotlight", "WindowManager", "Screenshot",
}


# ---------------------------------------------------------------- displays

def get_displays():
    """Return displays as dicts with id, name and bounds (global, top-left origin)."""
    import Quartz
    from AppKit import NSScreen

    names = {}
    for s in NSScreen.screens():
        did = int(s.deviceDescription()["NSScreenNumber"])
        names[did] = str(s.localizedName())

    err, ids, count = Quartz.CGGetActiveDisplayList(16, None, None)
    out = []
    for did in ids[:count]:
        b = Quartz.CGDisplayBounds(did)
        out.append({
            "id": int(did),
            "name": names.get(int(did), f"Display {did}"),
            "x": b.origin.x, "y": b.origin.y,
            "w": b.size.width, "h": b.size.height,
            "main": bool(Quartz.CGDisplayIsMain(did)),
        })
    # Stable order: left to right, then top to bottom.
    out.sort(key=lambda d: (d["x"], d["y"]))
    return out


def display_for_rect(displays, x, y, w, h):
    """Index of the display that holds most of the given rect, or None."""
    best, best_area = None, 0.0
    for i, d in enumerate(displays):
        ox = max(0.0, min(x + w, d["x"] + d["w"]) - max(x, d["x"]))
        oy = max(0.0, min(y + h, d["y"] + d["h"]) - max(y, d["y"]))
        if ox * oy > best_area:
            best, best_area = i, ox * oy
    return best


# ---------------------------------------------------------------- windows

def top_window_on_display(displays, idx):
    """Frontmost normal window whose area is mostly on display idx."""
    import Quartz

    opts = (Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements)
    my_pid = os.getpid()
    for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:
        if w.get("kCGWindowLayer", 1) != 0:
            continue
        if w.get("kCGWindowAlpha", 1) <= 0:
            continue
        owner = w.get("kCGWindowOwnerName", "")
        pid = w.get("kCGWindowOwnerPID")
        if owner in IGNORED_OWNERS or pid == my_pid:
            continue
        b = w.get("kCGWindowBounds", {})
        x, y, ww, hh = b.get("X", 0), b.get("Y", 0), b.get("Width", 0), b.get("Height", 0)
        if ww < 120 or hh < 80:
            continue
        if display_for_rect(displays, x, y, ww, hh) == idx:
            return {"pid": pid, "owner": owner, "title": w.get("kCGWindowName", ""),
                    "x": x, "y": y, "w": ww, "h": hh}
    return None


def _ax_get(el, attr):
    from ApplicationServices import AXUIElementCopyAttributeValue
    err, val = AXUIElementCopyAttributeValue(el, attr, None)
    return val if err == 0 else None


def _ax_rect(win):
    from ApplicationServices import AXValueGetValue, kAXValueCGPointType, kAXValueCGSizeType
    pos, size = _ax_get(win, "AXPosition"), _ax_get(win, "AXSize")
    if pos is None or size is None:
        return None
    _, p = AXValueGetValue(pos, kAXValueCGPointType, None)
    _, s = AXValueGetValue(size, kAXValueCGSizeType, None)
    return p.x, p.y, s.width, s.height


def frontmost_pid():
    """PID of the app with keyboard focus, read live.

    NSWorkspace.frontmostApplication goes stale in a process without a run
    loop, so ask Accessibility instead.
    """
    from ApplicationServices import AXUIElementCreateSystemWide, AXUIElementGetPid
    app = _ax_get(AXUIElementCreateSystemWide(), "AXFocusedApplication")
    if app is None:
        return None
    err, pid = AXUIElementGetPid(app, None)
    return pid if err == 0 else None


def focused_window_display(displays):
    """Display index of the frontmost app's top on-screen window.

    Uses the on-screen window list rather than the app's reported focused
    window, which some apps (e.g. Electron ones) report unreliably.
    """
    import Quartz

    pid = frontmost_pid()
    if pid is None:
        return None
    opts = (Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements)
    for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:
        if w.get("kCGWindowOwnerPID") != pid or w.get("kCGWindowLayer", 1) != 0:
            continue
        b = w.get("kCGWindowBounds", {})
        if b.get("Width", 0) < 120 or b.get("Height", 0) < 80:
            continue
        return display_for_rect(displays, b["X"], b["Y"], b["Width"], b["Height"])
    return None


def focus_window(target):
    """Bring the given CG window to front and make it key."""
    from ApplicationServices import (
        AXUIElementCreateApplication, AXUIElementPerformAction,
        AXUIElementSetAttributeValue,
    )
    from AppKit import NSRunningApplication

    ax_app = AXUIElementCreateApplication(target["pid"])
    match = None
    for win in _ax_get(ax_app, "AXWindows") or []:
        rect = _ax_rect(win)
        if rect and all(abs(a - b) <= 4 for a, b in
                        zip(rect, (target["x"], target["y"], target["w"], target["h"]))):
            match = win
            break

    # Make the app frontmost (Accessibility route works on recent macOS where
    # activating other apps is otherwise restricted), then raise the window.
    AXUIElementSetAttributeValue(ax_app, "AXFrontmost", True)
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(target["pid"])
    if app is not None:
        app.activateWithOptions_(2)  # NSApplicationActivateIgnoringOtherApps
    if match is not None:
        AXUIElementSetAttributeValue(match, "AXMain", True)
        AXUIElementPerformAction(match, "AXRaise")
    return match is not None


def warp_cursor(target):
    import Quartz
    Quartz.CGWarpMouseCursorPosition((target["x"] + target["w"] / 2,
                                      target["y"] + target["h"] / 2))
    Quartz.CGAssociateMouseAndMouseCursorPosition(True)


def check_accessibility():
    from ApplicationServices import AXIsProcessTrustedWithOptions
    ok = AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})
    if not ok:
        print("Accessibility permission is needed to switch windows.\n"
              "Grant it in System Settings > Privacy & Security > Accessibility "
              "for the app running this script (e.g. Terminal), then rerun.")
    return ok


# ---------------------------------------------------------------- head pose

class HeadPose:
    """Webcam -> (yaw, pitch) in degrees using MediaPipe Face Landmarker."""

    def __init__(self, camera=0, preview=False):
        import cv2
        from mediapipe.tasks.python import BaseOptions, vision

        self.cv2 = cv2
        self.cap = cv2.VideoCapture(camera)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not self.cap.isOpened():
            sys.exit("Could not open the camera. Check System Settings > Privacy & "
                     "Security > Camera for the app running this script.")
        self.landmarker = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=MODEL),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                output_facial_transformation_matrixes=True,
            ))
        self.t0 = time.monotonic()
        self.last_ts = -1
        self.preview = preview

    def read(self, label=""):
        """Return (yaw, pitch) or None if no face this frame."""
        import mediapipe as mp

        ok, frame = self.cap.read()
        if not ok:
            return None
        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        ts = int((time.monotonic() - self.t0) * 1000)
        if ts <= self.last_ts:
            ts = self.last_ts + 1
        self.last_ts = ts
        res = self.landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)

        pose = None
        if res.facial_transformation_matrixes:
            R = np.asarray(res.facial_transformation_matrixes[0])[:3, :3]
            yaw = math.degrees(math.atan2(R[0, 2], R[2, 2]))
            pitch = math.degrees(math.atan2(-R[1, 2], math.hypot(R[0, 2], R[2, 2])))
            pose = (yaw, pitch)

        if self.preview:
            txt = f"yaw {pose[0]:+.1f}  pitch {pose[1]:+.1f}" if pose else "no face"
            frame = self.cv2.flip(frame, 1)
            self.cv2.putText(frame, txt, (10, 30), self.cv2.FONT_HERSHEY_SIMPLEX,
                             0.8, (0, 255, 0), 2)
            if label:
                self.cv2.putText(frame, label, (10, 65), self.cv2.FONT_HERSHEY_SIMPLEX,
                                 0.8, (0, 200, 255), 2)
            self.cv2.imshow("headfocus", frame)
            self.cv2.waitKey(1)
        return pose

    def sample(self, seconds):
        vals, end = [], time.monotonic() + seconds
        while time.monotonic() < end:
            p = self.read()
            if p:
                vals.append(p)
        return vals

    def close(self):
        self.cap.release()
        if self.preview:
            self.cv2.destroyAllWindows()


# ---------------------------------------------------------------- commands

def cmd_displays(_args):
    displays = get_displays()
    for i, d in enumerate(displays):
        w = top_window_on_display(displays, i)
        top = f"{w['owner']} - {w['title']!r}" if w else "(no window)"
        print(f"[{i}] {d['name']}{' (main)' if d['main'] else ''}  "
              f"{int(d['w'])}x{int(d['h'])} at ({int(d['x'])},{int(d['y'])})  top: {top}")
    print("focused window is on display:", focused_window_display(displays))


def cmd_focus(args):
    if not check_accessibility():
        return
    displays = get_displays()
    w = top_window_on_display(displays, args.n)
    if not w:
        print("No window on that display.")
        return
    exact = focus_window(w)
    print(f"Focused {w['owner']} - {w['title']!r}" + ("" if exact else " (app only)"))


def cmd_calibrate(args):
    displays = get_displays()
    pose = HeadPose(args.camera)
    print("Calibration. Sit how you normally sit. For each display, turn your HEAD "
          "(not just your eyes) to face its center, press Enter, and hold still "
          "for 2 seconds.\n")
    pose.sample(1.0)  # warm up camera exposure
    centers = []
    for i, d in enumerate(displays):
        input(f"Look at [{i}] {d['name']} ({int(d['w'])}x{int(d['h'])}) and press Enter...")
        vals = pose.sample(2.0)
        if len(vals) < 5:
            pose.close()
            sys.exit("Couldn't see your face. Check lighting / camera and try again.")
        yaw, pitch = np.median(np.array(vals), axis=0)
        print(f"   yaw {yaw:+.1f}  pitch {pitch:+.1f}  ({len(vals)} frames)")
        centers.append({"id": d["id"], "name": d["name"],
                        "yaw": float(yaw), "pitch": float(pitch)})
    pose.close()

    for a in range(len(centers)):
        for b in range(a + 1, len(centers)):
            dist = math.hypot(centers[a]["yaw"] - centers[b]["yaw"],
                              centers[a]["pitch"] - centers[b]["pitch"])
            if dist < 8:
                print(f"\nWarning: {centers[a]['name']} and {centers[b]['name']} are only "
                      f"{dist:.1f} degrees apart. Turn your head more during calibration, "
                      "or switching between them may be unreliable.")

    with open(CONFIG, "w") as f:
        json.dump({"camera": args.camera, "displays": centers}, f, indent=2)
    print(f"\nSaved {CONFIG}. Try it with: ./headfocus run --preview")


def cmd_run(args):
    if not os.path.exists(CONFIG):
        sys.exit("No calibration yet. Run: ./headfocus calibrate")
    if not check_accessibility():
        sys.exit(1)  # non-zero so the login agent retries after permission is granted
    cfg = json.load(open(CONFIG))
    displays = get_displays()
    # Match calibrated displays by ID, falling back to name (macOS can give a
    # monitor a new ID after it sleeps or is reconnected).
    by_id = {d["id"]: i for i, d in enumerate(displays)}
    by_name = {d["name"]: i for i, d in enumerate(displays)}
    centers = []
    for c in cfg["displays"]:
        i = by_id.get(c["id"], by_name.get(c["name"]))
        if i is not None and i not in [x[0] for x in centers]:
            centers.append((i, np.array([c["yaw"], c["pitch"]]), c["name"]))
    if len(centers) < 2:
        sys.exit("Display setup changed since calibration. Run: ./headfocus calibrate")

    # Optional tuning in config.json (lets the login agent be tuned without new flags).
    args.dwell = cfg.get("dwell", args.dwell)
    args.margin = cfg.get("margin", args.margin)
    max_dist = cfg.get("max_dist", 22.0)  # farther than this from every display = looking away
    debug = cfg.get("debug", False)
    next_trace = 0.0

    pose = HeadPose(cfg.get("camera", args.camera), preview=args.preview)
    smoothed = None
    current = None        # display we last decided you're looking at
    candidate, since = None, 0.0
    alpha = 0.5           # smoothing (higher = more responsive)
    period = 1.0 / args.fps

    names = ", ".join(f"[{i}] {n}" for i, _, n in centers)
    log(f"Tracking {names}. dwell {args.dwell:.2f}s, margin {args.margin:.1f} deg.")
    layout = [d["id"] for d in displays]
    next_layout_check = time.monotonic() + 5
    try:
        while True:
            t = time.monotonic()
            if t >= next_layout_check:
                next_layout_check = t + 5
                if [d["id"] for d in get_displays()] != layout:
                    # Monitor plugged/unplugged: exit so the login agent restarts us
                    # with the new layout.
                    print("Display layout changed, restarting.")
                    sys.exit(3)
            p = pose.read(label=centers[[c[0] for c in centers].index(current)][2]
                          if current is not None else "")
            if debug and t >= next_trace:
                next_trace = t + 0.5
                log("pose " + (f"yaw {p[0]:+6.1f} pitch {p[1]:+6.1f}" if p else "no face")
                    + (f"  smoothed {smoothed[0]:+6.1f} {smoothed[1]:+6.1f}" if smoothed is not None else "")
                    + f"  current {current}")
            if p is None:
                candidate = None
            else:
                v = np.array(p)
                smoothed = v if smoothed is None else alpha * v + (1 - alpha) * smoothed
                dists = {i: float(np.linalg.norm(smoothed - c)) for i, c, _ in centers}
                nearest = min(dists, key=dists.get)

                # Looking away (phone, window, person): don't switch.
                if dists[nearest] > max_dist:
                    candidate = None
                # Hysteresis: only consider a switch when clearly closer to another display.
                elif current is None or (nearest != current and
                                       dists[current] - dists[nearest] > args.margin):
                    if candidate != nearest:
                        candidate, since = nearest, t
                    elif t - since >= args.dwell:
                        first = current is None
                        current, candidate = nearest, None
                        log(f"facing [{current}] yaw {smoothed[0]:+.1f} pitch {smoothed[1]:+.1f}"
                            + (" (startup, no focus change)" if first else ""))
                        if not first:  # don't steal focus at startup
                            on_switch(displays, current, args)
                else:
                    candidate = None

            dt = time.monotonic() - t
            if dt < period:
                time.sleep(period - dt)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        pose.close()


def log(msg):
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


def on_switch(displays, idx, args):
    name = displays[idx]["name"]
    if focused_window_display(displays) == idx:
        log(f"   {name}: already focused (pid {frontmost_pid()})")
        return
    w = top_window_on_display(displays, idx)
    if not w:
        log(f"   {name}: no window")
        return
    focus_window(w)
    if args.move_cursor:
        warp_cursor(w)
    log(f"   {name}: focused {w['owner']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("calibrate")
    c.add_argument("--camera", type=int, default=0)
    c.set_defaults(func=cmd_calibrate)

    r = sub.add_parser("run")
    r.add_argument("--camera", type=int, default=0)
    r.add_argument("--preview", action="store_true", help="show the camera window")
    r.add_argument("--dwell", type=float, default=0.3,
                   help="seconds you must face a display before it switches")
    r.add_argument("--margin", type=float, default=3.0,
                   help="degrees past the midpoint needed to switch (prevents flicker)")
    r.add_argument("--fps", type=float, default=15.0)
    r.add_argument("--move-cursor", action="store_true",
                   help="also move the mouse to the focused window")
    r.add_argument("-q", "--quiet", dest="verbose", action="store_false")
    r.set_defaults(func=cmd_run)

    d = sub.add_parser("displays")
    d.set_defaults(func=cmd_displays)

    f = sub.add_parser("focus")
    f.add_argument("n", type=int)
    f.set_defaults(func=cmd_focus)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
