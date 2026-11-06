"""
REWIND.exe - procedural pixel-art generator.

Generates every sprite sheet listed in the GDD (section 7.4 / 7.5) at 16 PPU,
using the GDD palette (section 7.2), and writes Assets/Art/art_manifest.json,
which the Unity editor script (Assets/Art/Editor/RewindArtPipeline.cs) uses to
slice sheets and build AnimationClips, Animator Controllers, prefabs and tiles.

Usage:  python Tools/ArtGen/generate_art.py            (from the project root)
        python Tools/ArtGen/generate_art.py --preview  (also writes preview PNGs)
"""
import json
import math
import os
import random
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ART = os.path.join(ROOT, "Assets", "Art")
PREVIEW_DIR = os.path.join(HERE, "preview")


# --------------------------------------------------------------------------
# Palette (GDD 7.2 + supporting ramps)
# --------------------------------------------------------------------------
def hexc(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


P = dict(
    ink=hexc("0A0F14"),  # outline
    bg=hexc("101820"),  # GDD Background
    bg2=hexc("16222C"),
    bg3=hexc("1C2A35"),
    m0=hexc("1A242C"),
    m1=hexc("24313A"),  # GDD Metal
    m2=hexc("34444F"),
    m3=hexc("4E6170"),
    m4=hexc("7590A0"),
    m5=hexc("A9BCC6"),
    g0=hexc("0C2A1C"),
    g1=hexc("1E6B45"),
    g2=hexc("36B36E"),
    g3=hexc("66FF99"),  # GDD CRT Green
    g4=hexc("C8FFE0"),
    a0=hexc("5A3E1C"),
    a1=hexc("9A6B2A"),
    a2=hexc("E4B65B"),  # GDD Warning
    a3=hexc("FFE29A"),
    r0=hexc("3A1216"),
    r1=hexc("7E2028"),
    r2=hexc("C8323C"),  # GDD Error (dark red, used sparingly)
    r3=hexc("FF7A70"),
    rust0=hexc("3E2418"),
    rust1=hexc("6E4026"),
    rust2=hexc("9C5A32"),
    skin=hexc("E0A878"),
    skin2=hexc("B07850"),
    hair=hexc("2A1E1A"),
    suit0=hexc("5E3B1E"),
    suit1=hexc("9C6230"),
    suit2=hexc("C98640"),
    boot=hexc("1A1A20"),
    boot2=hexc("32323C"),
    white=hexc("D8E0E6"),  # GDD Text
    tape=hexc("2E1C14"),
    tape2=hexc("4E3222"),
    paper=hexc("C9A577"),
    paper2=hexc("9C7A50"),
)
CLEAR = (0, 0, 0, 0)


def with_alpha(c, a):
    return (c[0], c[1], c[2], a)


# --------------------------------------------------------------------------
# Canvas helpers
# --------------------------------------------------------------------------
class Canvas:
    def __init__(self, w, h, fill=CLEAR):
        self.w, self.h = w, h
        self.im = Image.new("RGBA", (w, h), fill)
        self.px = self.im.load()

    def p(self, x, y, c):
        x, y = int(x), int(y)
        if c is not None and 0 <= x < self.w and 0 <= y < self.h:
            self.px[x, y] = c

    def get(self, x, y):
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.px[x, y]
        return CLEAR

    def rect(self, x, y, w, h, c):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.p(xx, yy, c)

    def hline(self, x0, x1, y, c):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            self.p(x, y, c)

    def vline(self, x, y0, y1, c):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            self.p(x, y, c)

    def box(self, x, y, w, h, c):
        self.hline(x, x + w - 1, y, c)
        self.hline(x, x + w - 1, y + h - 1, c)
        self.vline(x, y, y + h - 1, c)
        self.vline(x + w - 1, y, y + h - 1, c)

    def bevel(self, x, y, w, h, base, hi, lo, edge=None):
        """Filled panel with a 1px highlight on top/left and shadow on bottom/right."""
        self.rect(x, y, w, h, base)
        self.hline(x, x + w - 1, y, hi)
        self.vline(x, y, y + h - 1, hi)
        self.hline(x, x + w - 1, y + h - 1, lo)
        self.vline(x + w - 1, y, y + h - 1, lo)
        if edge:
            self.box(x - 1, y - 1, w + 2, h + 2, edge)

    def line(self, x0, y0, x1, y1, c, width=1):
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            for k in range(width):
                self.p(x0 + k, y0, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def disc(self, cx, cy, r, c):
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            for x in range(int(cx - r - 1), int(cx + r + 2)):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                    self.p(x, y, c)

    def ascii(self, x, y, rows, key):
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch in key:
                    self.p(x + i, y + j, key[ch])

    def blit(self, other, x, y):
        for yy in range(other.h):
            for xx in range(other.w):
                c = other.px[xx, yy]
                if c[3] > 0:
                    self.p(x + xx, y + yy, c)

    def outline(self, c=None, diagonal=False):
        """Adds a 1px outline around every opaque region (classic sprite outline)."""
        c = c or P["ink"]
        src = self.im.copy().load()
        nbrs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if diagonal:
            nbrs += [(1, 1), (-1, -1), (1, -1), (-1, 1)]
        for y in range(self.h):
            for x in range(self.w):
                if src[x, y][3] != 0:
                    continue
                for dx, dy in nbrs:
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < self.w and 0 <= yy < self.h and src[xx, yy][3] == 255:
                        self.px[x, y] = c
                        break
        return self

    def flip_x(self):
        c = Canvas(self.w, self.h)
        c.im = self.im.transpose(Image.FLIP_LEFT_RIGHT)
        c.px = c.im.load()
        return c


# --------------------------------------------------------------------------
# 5x7 pixel font (used for keycaps, signs, logo)
# --------------------------------------------------------------------------
FONT = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "e": [".....", ".....", ".###.", "#...#", "#####", "#....", ".###."],
    "x": [".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    ".": [".....", ".....", ".....", ".....", ".....", ".....", "..#.."],
    "!": ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."],
    ">": [".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."],
    "<": ["...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."],
    "_": [".....", ".....", ".....", ".....", ".....", ".....", "#####"],
    "[": [".###.", ".#...", ".#...", ".#...", ".#...", ".#...", ".###."],
    "]": [".###.", "...#.", "...#.", "...#.", "...#.", "...#.", ".###."],
    "LEFT": [".....", "..#..", ".#...", "#####", ".#...", "..#..", "....."],
    "RIGHT": [".....", "..#..", "...#.", "#####", "...#.", "..#..", "....."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
}


def text_width(s, scale=1, spacing=1):
    return len(s) * (5 + spacing) * scale - spacing * scale


def draw_text(c, x, y, s, col, scale=1, spacing=1):
    cx = x
    for ch in s:
        g = FONT.get(ch, FONT[" "])
        for j, row in enumerate(g):
            for i, bit in enumerate(row):
                if bit == "#":
                    c.rect(cx + i * scale, y + j * scale, scale, scale, col)
        cx += (5 + spacing) * scale


def draw_glyph(c, x, y, key, col):
    for j, row in enumerate(FONT[key]):
        for i, bit in enumerate(row):
            if bit == "#":
                c.p(x + i, y + j, col)


# --------------------------------------------------------------------------
# Sheet + manifest bookkeeping
# --------------------------------------------------------------------------
MANIFEST = {"sheets": [], "controllers": []}
PREVIEWS = []


def save_sheet(rel_path, frames, cols=None, pivot=(0.5, 0.5), border=(0, 0, 0, 0),
               animations=None, tiles=None, group=None, wrap_repeat=False):
    fw, fh = frames[0].w, frames[0].h
    n = len(frames)
    cols = cols or n
    rows = (n + cols - 1) // cols
    sheet = Image.new("RGBA", (fw * cols, fh * rows), CLEAR)
    for i, f in enumerate(frames):
        sheet.paste(f.im, ((i % cols) * fw, (i // cols) * fh))
    out = os.path.join(ROOT, rel_path.replace("/", os.sep))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    entry = {
        "path": rel_path,
        "group": group or os.path.splitext(os.path.basename(rel_path))[0],
        "frameWidth": fw,
        "frameHeight": fh,
        "frameCount": n,
        "pivotX": pivot[0],
        "pivotY": pivot[1],
        "border": list(border),
        "animations": [
            {"name": a[0], "frames": list(a[1]), "fps": a[2], "loop": a[3]} for a in (animations or [])
        ],
        "tileFrames": (tiles or {}).get("solid", []),
        "tileFramesNoCollider": (tiles or {}).get("decor", []),
        "wrapRepeat": wrap_repeat,
    }
    MANIFEST["sheets"].append(entry)
    PREVIEWS.append((rel_path, sheet))
    print(f"  {rel_path:62s} {fw}x{fh} x{n}")
    return entry


def controller(name, sheet, default, states, params=(), transitions=(), sorting=0, folder=None):
    """states: [(stateName, clipName)], params: [(name, type)],
    transitions: [(from, to, hasExitTime, [(param, mode, threshold)])]  from may be 'Any'."""
    MANIFEST["controllers"].append({
        "name": name,
        "sheet": sheet["path"],
        "folder": folder or sheet["group"],
        "defaultState": default,
        "sortingOrder": sorting,
        "parameters": [{"name": p[0], "type": p[1]} for p in params],
        "states": [{"name": s[0], "clip": s[1]} for s in states],
        "transitions": [
            {"from": t[0], "to": t[1], "hasExitTime": t[2], "exitTime": 1.0 if t[2] else 0.0,
             "conditions": [{"parameter": c[0], "mode": c[1], "threshold": float(c[2])} for c in t[3]]}
            for t in transitions
        ],
    })


def mode_controller(name, sheet, mode_states, sorting=0, param="Mode"):
    """Any State -> state when the int parameter equals the state's index."""
    controller(
        name, sheet, mode_states[0][0], mode_states, params=[(param, "Int")],
        transitions=[("Any", s[0], False, [(param, "Equals", i)]) for i, s in enumerate(mode_states)],
        sorting=sorting,
    )


def bool_toggle_controller(name, sheet, prefix, param, sorting=0):
    """Off / TurningOn / On / TurningOff driven by a bool."""
    controller(
        name, sheet, "Off",
        [("Off", f"{prefix}_Off"), ("TurningOn", f"{prefix}_TurningOn"),
         ("On", f"{prefix}_On"), ("TurningOff", f"{prefix}_TurningOff")],
        params=[(param, "Bool")],
        transitions=[
            ("Off", "TurningOn", False, [(param, "If", 0)]),
            ("TurningOn", "On", True, []),
            ("On", "TurningOff", False, [(param, "IfNot", 0)]),
            ("TurningOff", "Off", True, []),
        ],
        sorting=sorting,
    )


# ==========================================================================
# CHARACTER - the Operator (24x24 frames, pivot bottom-centre)
# ==========================================================================
HEAD = [
    "..hhhhh.",
    ".hhhhhhh",
    "hhhhhhss",
    "hhmmssEs",
    "hmgmssss",
    ".hmmsssS",
    "..hkkkks",
    "...sSSs.",
]
HEAD_KEY = None  # filled lazily (needs palette)


def operator_frame(bob=0, back=(-1, 0), front=(2, 0), back_hand=(-1, 5), front_hand=(1, 5),
                   pack_led=True, spark=False, squash=0):
    """back/front = (foot x offset from hip, lift); hands = (dx, dy) from shoulder."""
    key = {
        "h": P["hair"], "s": P["skin"], "S": P["skin2"], "E": P["ink"],
        "m": P["m3"], "g": P["g3"], "k": P["m1"],
    }
    c = Canvas(24, 24)
    top = 3 + bob + squash
    hip_y = 17 + bob + squash
    sh_y = top + 9  # shoulder row

    # back arm (behind body)
    bx, by = 11, sh_y
    hx, hy = bx + back_hand[0], by + back_hand[1]
    c.line(bx, by, hx, hy - 1, P["suit0"], width=2)
    c.rect(hx, hy - 1, 2, 2, P["skin2"])

    # back leg
    def leg(hipx, off, lift, col):
        fx, fy = hipx + off, 22 - lift
        c.line(hipx, hip_y, fx, fy - 2, col, width=2)
        c.rect(fx, fy - 1, 3, 2, P["boot"])
        c.p(fx, fy - 1, P["boot2"])

    leg(10, back[0], back[1], P["suit0"])

    # backpack tape unit
    c.rect(6, top + 8, 3, 6, P["m2"])
    c.vline(6, top + 8, top + 13, P["m3"])
    c.p(7, top + 10, P["a2"] if pack_led else P["a0"])
    c.p(7, top + 12, P["m1"])

    # torso
    tx, ty = 9, top + 8
    c.rect(tx, ty, 6, 6 - min(squash, 1), P["suit1"])
    c.vline(tx, ty, ty + 5, P["suit0"])
    c.hline(tx + 1, tx + 5, ty, P["suit2"])
    belt = ty + 4 - min(squash, 1)
    c.hline(tx, tx + 5, belt, P["boot"])
    c.p(tx + 4, belt, P["g3"])
    c.rect(tx, hip_y, 6, 1, P["suit0"])

    # front leg
    leg(12, front[0], front[1], P["suit1"])

    # head
    c.ascii(8, top, HEAD, key)

    # front arm
    fx0, fy0 = 12, sh_y
    hx, hy = fx0 + front_hand[0], fy0 + front_hand[1]
    c.line(fx0, fy0, hx, hy - 1, P["suit2"], width=2)
    c.rect(hx, hy - 1, 2, 2, P["skin"])
    if spark:
        c.p(hx + 2, hy - 1, P["g4"])
    c.outline()
    if spark:
        c.p(hx + 3, hy - 2, P["g3"])
        c.p(hx + 3, hy, P["g2"])
    return c


def gen_operator():
    frames = []
    # Idle (0-3): breathing + backpack LED blink
    for i, b in enumerate([0, 0, 1, 1]):
        frames.append(operator_frame(bob=b, pack_led=i < 2))
    # Walk (4-9)
    offs = [3, 1, -1, -3, -1, 1]
    lifts = [0, 0, 0, 0, 1, 1]
    for t in range(6):
        a, b = t, (t + 3) % 6
        bob = 1 if t in (0, 3) else 0
        frames.append(operator_frame(
            bob=bob, front=(offs[a] - 1, lifts[a]), back=(offs[b] - 1, lifts[b]),
            front_hand=(-offs[a] // 2, 5), back_hand=(offs[a] // 2 - 1, 5),
            pack_led=t < 3))
    # Jump (10), Fall (11), Land (12)
    frames.append(operator_frame(back=(-2, 3), front=(2, 2), back_hand=(-2, -4), front_hand=(2, -4)))
    frames.append(operator_frame(back=(-2, 0), front=(3, 1), back_hand=(-4, -2), front_hand=(4, -3)))
    frames.append(operator_frame(squash=2, back=(-3, 0), front=(3, 0), back_hand=(-2, 3), front_hand=(3, 3)))
    # Interact (13-15): reach forward to a panel
    frames.append(operator_frame(front_hand=(3, 3)))
    frames.append(operator_frame(front_hand=(5, 1)))
    frames.append(operator_frame(front_hand=(6, 0), spark=True))
    # Rewind glitch (16-17): operator snaps back to start (tinted copies)
    for tint in (P["a2"], P["g3"]):
        f = operator_frame()
        for y in range(24):
            shift = (1 if y % 4 < 2 else -1) if tint == P["a2"] else (2 if y % 6 == 0 else 0)
            row = [f.px[x, y] for x in range(24)]
            for x in range(24):
                src = row[(x - shift) % 24]
                if src[3]:
                    r = (src[0] + tint[0]) // 2, (src[1] + tint[1]) // 2, (src[2] + tint[2]) // 2
                    f.px[x, y] = (r[0], r[1], r[2], 255 if y % 2 else 170)
                else:
                    f.px[x, y] = CLEAR
        frames.append(f)
    # Collapse (18 kneel, 19 lying on the floor) - used by the fail ending
    frames.append(operator_frame(squash=4, back=(-3, 0), front=(3, 0), back_hand=(-1, 3), front_hand=(3, 4), pack_led=False))
    lying = Canvas(24, 24)
    rot = operator_frame(pack_led=False).im.transpose(Image.ROTATE_270)  # head to the right
    bbox = rot.getbbox()
    lying.im.paste(rot, (0, 23 - bbox[3] + 1), rot)
    lying.px = lying.im.load()
    frames.append(lying)

    sheet = save_sheet(
        "Assets/Art/Characters/Operator/operator.png", frames, cols=6, pivot=(0.5, 0.0),
        group="Operator",
        animations=[
            ("Operator_Idle", [0, 1, 2, 3], 4, True),
            ("Operator_Walk", [4, 5, 6, 7, 8, 9], 10, True),
            ("Operator_Jump", [10], 10, False),
            ("Operator_Fall", [11], 10, False),
            ("Operator_Land", [12, 0], 12, False),
            ("Operator_Interact", [13, 14, 15, 15, 14, 13], 14, False),
            ("Operator_Rewind", [16, 17, 16, 17, 0], 16, False),
            ("Operator_Collapse", [12, 18, 18, 18, 19], 5, False),
            ("Operator_Dead", [19], 1, True),
        ])
    controller(
        "Operator", sheet, "Idle",
        [("Idle", "Operator_Idle"), ("Walk", "Operator_Walk"), ("Jump", "Operator_Jump"),
         ("Fall", "Operator_Fall"), ("Land", "Operator_Land"), ("Interact", "Operator_Interact"),
         ("Rewind", "Operator_Rewind"), ("Collapse", "Operator_Collapse"), ("Dead", "Operator_Dead")],
        params=[("Speed", "Float"), ("VelocityY", "Float"), ("Grounded", "Bool"),
                ("Interact", "Trigger"), ("Rewind", "Trigger"), ("Collapse", "Trigger")],
        transitions=[
            ("Idle", "Walk", False, [("Speed", "Greater", 0.1), ("Grounded", "If", 0)]),
            ("Walk", "Idle", False, [("Speed", "Less", 0.1)]),
            ("Idle", "Jump", False, [("Grounded", "IfNot", 0), ("VelocityY", "Greater", 0.1)]),
            ("Walk", "Jump", False, [("Grounded", "IfNot", 0), ("VelocityY", "Greater", 0.1)]),
            ("Idle", "Fall", False, [("Grounded", "IfNot", 0), ("VelocityY", "Less", -0.1)]),
            ("Walk", "Fall", False, [("Grounded", "IfNot", 0), ("VelocityY", "Less", -0.1)]),
            ("Jump", "Fall", False, [("VelocityY", "Less", 0.0)]),
            ("Jump", "Land", False, [("Grounded", "If", 0)]),
            ("Fall", "Land", False, [("Grounded", "If", 0)]),
            ("Land", "Walk", False, [("Speed", "Greater", 0.1)]),
            ("Land", "Idle", True, []),
            ("Idle", "Interact", False, [("Interact", "If", 0)]),
            ("Walk", "Interact", False, [("Interact", "If", 0)]),
            ("Interact", "Idle", True, []),
            ("Any", "Rewind", False, [("Rewind", "If", 0)]),
            ("Rewind", "Idle", True, []),
            ("Any", "Collapse", False, [("Collapse", "If", 0)]),
            ("Collapse", "Dead", True, []),
        ],
        sorting=10)


# ==========================================================================
# ENVIRONMENT - 16x16 tileset (8 x 4)
# ==========================================================================
def rivet(c, x, y):
    c.p(x, y, P["m4"])
    c.p(x + 1, y + 1, P["m0"])


def solid_tile(top=False, bottom=False, left=False, right=False, seed=0):
    rnd = random.Random(seed)
    c = Canvas(16, 16, P["m1"])
    # plate seams + grime
    c.hline(0, 15, 8, P["m0"])
    c.vline(8 if seed % 2 else 4, 0, 7, P["m0"])
    c.vline(12 if seed % 2 else 10, 9, 15, P["m0"])
    for _ in range(2):
        c.p(rnd.randrange(16), rnd.randrange(16), P["m2"])
    if seed % 2:
        c.p(rnd.randrange(16), rnd.randrange(9, 16), P["rust0"])
    if top:
        c.rect(0, 0, 16, 4, P["m2"])
        c.hline(0, 15, 0, P["ink"])
        c.hline(0, 15, 1, P["m5"])
        c.hline(0, 15, 2, P["m4"])
        c.hline(0, 15, 4, P["m0"])
        for x in (3, 11):
            c.p(x, 3, P["m1"])
        if seed % 3 == 0:
            c.p(6, 2, P["rust2"])
            c.p(7, 3, P["rust1"])
    if bottom:
        c.hline(0, 15, 15, P["ink"])
        c.hline(0, 15, 14, P["m0"])
    if left:
        c.vline(0, 0, 15, P["ink"])
        c.vline(1, 1 if top else 0, 15, P["m2"])
        if top:
            c.p(1, 1, P["m5"])
    if right:
        c.vline(15, 0, 15, P["ink"])
        c.vline(14, 1 if top else 0, 15, P["m0"])
    if top and left:
        c.p(0, 0, CLEAR)
    if top and right:
        c.p(15, 0, CLEAR)
    if not top:
        rivet(c, 2 if not left else 3, 2)
        rivet(c, 12 if not right else 11, 11)
    return c


def inner_corner(corner):
    c = solid_tile(seed=7)
    pts = {"TL": (0, 0), "TR": (15, 0), "BL": (0, 15), "BR": (15, 15)}[corner]
    x, y = pts
    sx = 1 if x == 0 else -1
    sy = 1 if y == 0 else -1
    c.p(x, y, P["ink"])
    c.p(x + sx, y, P["m4"] if y == 0 else P["m0"])
    c.p(x, y + sy, P["m2"] if x == 0 else P["m0"])
    return c


def platform_piece(kind):
    c = Canvas(16, 16)
    c.rect(0, 0, 16, 5, P["m2"])
    c.hline(0, 15, 0, P["ink"])
    c.hline(0, 15, 1, P["m5"])
    c.hline(0, 15, 4, P["m0"])
    c.hline(0, 15, 5, P["ink"])
    for x in range(1, 16, 3):
        c.p(x, 3, P["m1"])
    if kind in ("L", "R"):
        ex = 0 if kind == "L" else 15
        c.vline(ex, 0, 5, P["ink"])
        c.p(ex, 0, CLEAR)
        # support strut
        sx = 3 if kind == "L" else 11
        c.line(sx, 6, sx + (2 if kind == "L" else -2), 10, P["m1"], width=2)
        c.p(sx + (3 if kind == "L" else -2), 11, P["ink"])
    else:
        c.vline(7, 6, 8, P["m1"])
        c.vline(8, 6, 8, P["m0"])
    return c


def hazard_top():
    c = solid_tile(top=True, seed=4)
    for x in range(16):
        for y in range(1, 4):
            c.p(x, y, P["a2"] if ((x + y) // 2) % 2 == 0 else P["ink"])
    return c


def grate_top():
    c = solid_tile(top=True, seed=5)
    for x in range(1, 16, 2):
        c.vline(x, 1, 3, P["m0"])
    return c


def wall_base(seed=0):
    rnd = random.Random(100 + seed)
    c = Canvas(16, 16, P["bg2"])
    c.box(0, 0, 16, 16, P["bg"])
    c.hline(1, 14, 1, P["bg3"])
    for _ in range(4):
        c.p(rnd.randrange(1, 15), rnd.randrange(2, 15), P["bg3"])
    return c


def wall_rivets():
    c = wall_base(1)
    for x, y in ((2, 2), (12, 2), (2, 12), (12, 12)):
        c.p(x, y, P["m2"])
        c.p(x + 1, y + 1, P["bg"])
    return c


def wall_vent():
    c = wall_base(2)
    c.rect(3, 4, 10, 8, P["bg"])
    for y in range(5, 12, 2):
        c.hline(4, 11, y, P["m1"])
    c.box(2, 3, 12, 10, P["m1"])
    return c


def pipe_h():
    c = Canvas(16, 16)
    c.rect(0, 5, 16, 6, P["m2"])
    c.hline(0, 15, 4, P["ink"])
    c.hline(0, 15, 6, P["m4"])
    c.hline(0, 15, 9, P["m1"])
    c.hline(0, 15, 11, P["ink"])
    c.rect(6, 4, 3, 8, P["m3"])
    c.vline(6, 4, 11, P["ink"])
    c.vline(8, 4, 11, P["ink"])
    return c


def pipe_v():
    c = Canvas(16, 16)
    c.rect(5, 0, 6, 16, P["m2"])
    c.vline(4, 0, 15, P["ink"])
    c.vline(6, 0, 15, P["m4"])
    c.vline(9, 0, 15, P["m1"])
    c.vline(11, 0, 15, P["ink"])
    c.rect(4, 6, 8, 3, P["m3"])
    c.hline(4, 11, 6, P["ink"])
    c.hline(4, 11, 8, P["ink"])
    return c


def pipe_corner():
    c = Canvas(16, 16)
    c.rect(5, 5, 11, 6, P["m2"])
    c.rect(5, 5, 6, 11, P["m2"])
    c.hline(5, 15, 4, P["ink"])
    c.vline(4, 4, 15, P["ink"])
    c.hline(11, 15, 11, P["ink"])
    c.vline(11, 11, 15, P["ink"])
    c.hline(6, 15, 6, P["m4"])
    c.vline(6, 6, 15, P["m4"])
    c.rect(9, 9, 2, 2, P["m1"])
    return c


def pipe_joint():
    c = pipe_h()
    c.rect(5, 2, 6, 12, P["m3"])
    c.box(5, 2, 6, 12, P["ink"])
    c.rect(7, 0, 2, 2, P["r1"])  # valve wheel
    c.hline(5, 10, 0, P["r2"])
    return c


def wall_cables():
    c = wall_base(3)
    for x0, col in ((3, P["r1"]), (6, P["m0"]), (9, P["g1"]), (12, P["ink"])):
        for y in range(16):
            c.p(x0 + int(1.2 * math.sin(y / 3 + x0)), y, col)
    return c


def wall_warn():
    c = wall_base(4)
    c.rect(3, 3, 10, 10, P["a1"])
    c.box(3, 3, 10, 10, P["ink"])
    c.rect(4, 4, 8, 8, P["a2"])
    c.vline(8, 5, 9, P["ink"])
    c.p(8, 11, P["ink"])
    return c


def wall_lamp(on=True):
    c = wall_base(5)
    c.rect(5, 5, 6, 6, P["m1"])
    c.rect(6, 6, 4, 4, P["g2"] if on else P["g0"])
    c.p(6, 6, P["g4"] if on else P["g1"])
    return c


def wall_broken():
    c = wall_base(6)
    c.rect(4, 5, 8, 7, P["ink"])
    c.p(4, 5, P["bg2"])
    c.p(11, 11, P["bg2"])
    c.line(5, 7, 10, 10, P["r1"])
    c.line(6, 11, 9, 6, P["a1"])
    c.p(7, 8, P["a2"])
    return c


def plate_number():
    c = wall_base(7)
    c.rect(2, 4, 12, 9, P["m1"])
    c.box(2, 4, 12, 9, P["ink"])
    # "01" with tiny 3x5 digits
    for (x, rows) in ((4, ["###", "#.#", "#.#", "#.#", "###"]), (9, [".#.", "##.", ".#.", ".#.", "###"])):
        for j, r in enumerate(rows):
            for i, b in enumerate(r):
                if b == "#":
                    c.p(x + i, 6 + j, P["a2"])
    return c


def wall_dark():
    c = Canvas(16, 16, P["bg"])
    for x in range(0, 16, 4):
        c.vline(x, 0, 15, P["bg2"])
    return c


def gen_tileset():
    t = []
    t += [solid_tile(top=True, left=True, seed=1), solid_tile(top=True, seed=2),
          solid_tile(top=True, right=True, seed=3),
          platform_piece("L"), platform_piece("M"), platform_piece("R"),
          solid_tile(True, True, True, True, seed=6), hazard_top()]
    t += [solid_tile(left=True, seed=8), solid_tile(seed=9), solid_tile(right=True, seed=10),
          inner_corner("TL"), inner_corner("TR"), inner_corner("BL"), inner_corner("BR"), grate_top()]
    t += [solid_tile(bottom=True, left=True, seed=11), solid_tile(bottom=True, seed=12),
          solid_tile(bottom=True, right=True, seed=13),
          wall_base(0), wall_rivets(), wall_vent(), pipe_h(), pipe_v()]
    t += [pipe_corner(), wall_cables(), wall_warn(), wall_lamp(True), wall_broken(), plate_number(),
          wall_dark(), pipe_joint()]
    save_sheet("Assets/Art/Environment/Tiles/tileset_complex.png", t, cols=8, pivot=(0.5, 0.5),
               group="Tileset",
               tiles={"solid": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
                      "decor": list(range(19, 32))})


# ==========================================================================
# ENVIRONMENT - parallax backgrounds (320x180)
# ==========================================================================
def gen_backgrounds():
    rnd = random.Random(42)
    W, H = 320, 180
    far = Canvas(W, H, P["bg"])
    # vertical gradient
    for y in range(H):
        t = y / H
        col = tuple(int(P["bg"][i] * (1 - t * 0.5) + P["bg2"][i] * t * 0.5) for i in range(3)) + (255,)
        far.hline(0, W - 1, y, col)
    # server racks silhouettes
    x = 0
    while x < W:
        w = rnd.choice([18, 22, 26])
        h = rnd.randint(70, 120)
        top = H - 30 - h
        far.rect(x, top, w, h, P["bg3"])
        far.vline(x, top, top + h - 1, P["m0"])
        for yy in range(top + 6, top + h - 6, 6):
            far.hline(x + 3, x + w - 4, yy, P["bg2"])
            for led in range(x + 4, x + w - 4, 4):
                r = rnd.random()
                if r < 0.18:
                    far.p(led, yy + 2, P["g1"])
                elif r < 0.24:
                    far.p(led, yy + 2, P["a1"])
                elif r < 0.26:
                    far.p(led, yy + 2, P["r1"])
        x += w + rnd.choice([2, 4, 10])
    # girders
    for gx in range(30, W, 80):
        far.rect(gx, 0, 6, H, P["m0"])
        far.vline(gx, 0, H - 1, P["bg3"])
        for yy in range(0, H, 24):
            far.line(gx + 6, yy, gx + 30, yy + 24, P["m0"])
    # ceiling pipes
    for py, ph in ((10, 6), (20, 4)):
        far.rect(0, py, W, ph, P["m0"])
        far.hline(0, W - 1, py, P["bg3"])
    # floor haze
    for y in range(H - 40, H):
        a = (y - (H - 40)) / 40
        for xx in range(W):
            base = far.px[xx, y]
            far.px[xx, y] = tuple(int(base[i] * (1 - a * 0.6) + P["bg"][i] * a * 0.6) for i in range(3)) + (255,)

    mid = Canvas(W, H)
    # hanging cables (tile seamlessly: positions wrap)
    for i in range(9):
        x0 = rnd.randrange(W)
        span = rnd.randint(30, 70)
        sag = rnd.randint(8, 30)
        col = rnd.choice([P["ink"], P["m0"], P["rust0"]])
        for t in range(span * 2):
            xx = x0 + t / 2
            yy = 4 + sag * math.sin(math.pi * t / (span * 2))
            mid.p(int(xx) % W, int(yy), col)
    # catwalk silhouette with railing
    cy = 118
    mid.rect(0, cy, W, 3, P["m0"])
    mid.hline(0, W - 1, cy, P["m1"])
    mid.hline(0, W - 1, cy - 8, P["m0"])
    for xx in range(0, W, 10):
        mid.vline(xx, cy - 8, cy, P["m0"])
    for xx in range(4, W, 40):
        mid.line(xx, cy + 3, xx + 14, cy + 30, P["m0"], width=2)
    # big vertical pipe pairs
    for px_ in (60, 220):
        mid.rect(px_, 0, 7, H, P["m0"])
        mid.vline(px_ + 1, 0, H - 1, P["m1"])
        mid.rect(px_ + 10, 0, 4, H, P["m0"])
        for yy in range(12, H, 36):
            mid.rect(px_ - 1, yy, 9, 3, P["m1"])

    for p in (far, mid):
        p.w, p.h = W, H
    save_sheet("Assets/Art/Environment/Backgrounds/bg_far.png", [far], pivot=(0.5, 0.5), group="Backgrounds")
    save_sheet("Assets/Art/Environment/Backgrounds/bg_mid.png", [mid], pivot=(0.5, 0.5), group="Backgrounds")


def _bg_canvas(top, bottom):
    W, H = 320, 180
    c = Canvas(W, H)
    for y in range(H):
        t = y / (H - 1)
        c.hline(0, W - 1, y, tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3)) + (255,))
    return c


def _darken(c, amount, toward=None):
    """Push a background towards the base colour so foreground objects read clearly."""
    toward = toward or P["bg"]
    for y in range(c.h):
        for x in range(c.w):
            p = c.px[x, y]
            c.px[x, y] = tuple(int(p[i] * (1 - amount) + toward[i] * amount) for i in range(3)) + (255,)


def _glow(c, cx, cy, r, col, strength=0.35):
    for y in range(max(0, int(cy - r)), min(c.h, int(cy + r))):
        for x in range(max(0, int(cx - r)), min(c.w, int(cx + r))):
            d = math.hypot(x - cx, y - cy) / r
            if d < 1:
                a = (1 - d) ** 2 * strength
                p = c.px[x, y]
                c.px[x, y] = tuple(int(p[i] * (1 - a) + col[i] * a) for i in range(3)) + (255,)


def gen_bg_archive():
    """Room 2 - Tape Archive: shelving units full of reels."""
    rnd = random.Random(7)
    c = _bg_canvas(P["bg"], hexc("1A1E22"))
    W, H = c.w, c.h
    for sx in range(-20, W, 68):
        top, bottom = 26, H - 26
        c.rect(sx, top, 58, bottom - top, P["m0"])
        c.vline(sx, top, bottom, P["m1"])
        c.vline(sx + 57, top, bottom, P["ink"])
        for by in range(top + 22, bottom, 22):
            for rx in range(sx + 7, sx + 54, 11):
                if rnd.random() < 0.85:
                    draw_reel(c, rx, by - 6, 4.8, rnd.randrange(120), rnd.uniform(2.4, 4.6))
            c.rect(sx + 1, by, 56, 2, P["m2"])
            c.hline(sx + 1, sx + 56, by + 2, P["ink"])
        # label plates
        c.rect(sx + 20, top + 3, 18, 5, P["paper2"])
        c.hline(sx + 22, sx + 35, top + 5, P["rust0"])
    for lx in (60, 160, 260):  # hanging lamps
        c.vline(lx, 0, 10, P["ink"])
        c.rect(lx - 3, 10, 7, 3, P["m2"])
        c.rect(lx - 1, 13, 3, 1, P["a3"])
        _glow(c, lx, 22, 46, P["a2"], 0.22)
    _darken(c, 0.45)
    save_sheet("Assets/Art/Environment/Backgrounds/bg_archive.png", [c], pivot=(0.5, 0.5), group="Backgrounds")


def gen_bg_generator():
    """Room 3 - Generator Hall: turbines, heavy pipes, hazard paint."""
    c = _bg_canvas(hexc("120E10"), P["bg2"])
    W, H = c.w, c.h
    c.rect(0, 22, W, 10, P["m1"])  # main pipe
    c.hline(0, W - 1, 23, P["m3"])
    c.hline(0, W - 1, 31, P["ink"])
    for jx in range(10, W, 44):
        c.rect(jx, 20, 5, 14, P["m2"])
    for tx in (20, 128, 236):
        w, top, bottom = 64, 44, H - 28
        for x in range(w):
            shade = math.sin(math.pi * x / (w - 1))
            col = [P["m0"], P["m1"], P["m2"], P["m3"]][min(3, int(shade * 3.6))]
            c.vline(tx + x, top, bottom, col)
        for y in range(top + 10, bottom, 16):
            c.hline(tx, tx + w - 1, y, P["ink"])
        for y in range(bottom - 18, bottom - 10):
            for x in range(tx, tx + w):
                if ((x + y) // 4) % 2 == 0:
                    c.p(x, y, P["a1"])
        c.rect(tx + 8, top - 6, w - 16, 6, P["m2"])  # cap
        c.vline(tx + w // 2, 32, top - 6, P["m1"])
        c.rect(tx + w // 2 - 2, top + 3, 4, 3, P["r2"])
        _glow(c, tx + w // 2, top + 4, 26, P["r2"], 0.25)
    for y in range(H - 22, H):  # floor-level hazard band
        for x in range(W):
            if ((x + y) // 6) % 2 == 0:
                c.p(x, y, P["a0"])
    _darken(c, 0.42)
    save_sheet("Assets/Art/Environment/Backgrounds/bg_generator.png", [c], pivot=(0.5, 0.5), group="Backgrounds")


def gen_bg_core():
    """Room 4 - Core: a giant tape reel in the dark, cables radiating outwards."""
    rnd = random.Random(47)
    c = _bg_canvas(hexc("140A0E"), P["bg"])
    W, H = c.w, c.h
    cx, cy, R = 160, 82, 64
    for _ in range(26):  # cables to the edges
        a = rnd.uniform(0, math.tau)
        ex, ey = cx + math.cos(a) * 260, cy + math.sin(a) * 200
        c.line(cx + math.cos(a) * R, cy + math.sin(a) * R, ex, ey, rnd.choice([P["ink"], P["m0"], P["rust0"]]))
    for y in range(cy - R - 1, cy + R + 2):
        for x in range(cx - R - 1, cx + R + 2):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if d > R:
                continue
            ang = math.degrees(math.atan2(y - cy, x - cx)) % 120
            if d > R - 3:
                col = P["m3"]
            elif d < 9:
                col = P["m4"] if d > 3 else P["ink"]
            elif 20 < ang < 100 and d > 14:
                col = P["tape"] if d < 44 else P["bg2"]
            else:
                col = P["m2"]
            c.p(x, y, col)
    for sx in list(range(0, 70, 17)) + list(range(252, W, 17)):  # racks
        h = rnd.randint(50, 80)
        c.rect(sx, H - 24 - h, 15, h, P["m0"])
        for yy in range(H - 20 - h, H - 26, 5):
            if rnd.random() < 0.5:
                c.p(sx + rnd.randint(3, 11), yy, rnd.choice([P["r1"], P["g1"], P["a1"]]))
    for gx in (20, 300):
        _glow(c, gx, 10, 90, P["r2"], 0.28)
    _darken(c, 0.38)
    save_sheet("Assets/Art/Environment/Backgrounds/bg_core.png", [c], pivot=(0.5, 0.5), group="Backgrounds")


# ==========================================================================
# OBJECTS
# ==========================================================================
def draw_reel(c, cx, cy, r, angle, tape_r, spokes=3):
    """Reel-to-reel spool with rotating spoke holes."""
    for y in range(int(cy - r - 1), int(cy + r + 2)):
        for x in range(int(cx - r - 1), int(cx + r + 2)):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            d = math.hypot(dx, dy)
            if d > r:
                continue
            a = (math.degrees(math.atan2(dy, dx)) - angle) % (360 / spokes)
            if d > r - 1:
                col = P["m5"] if dy < -dx * 0.3 else P["m3"]
            elif d < 1.3:
                col = P["ink"] if d < 0.6 else P["m5"]
            elif d < 2.2:
                col = P["m4"]
            elif (360 / spokes) * 0.18 < a < (360 / spokes) * 0.82:
                col = P["tape2"] if d < tape_r else P["m0"]
                if d < tape_r and d > tape_r - 1:
                    col = P["tape"]
            else:
                col = P["m4"]
            c.p(x, y, col)


def gen_tape_recorder():
    frames = []

    def deck(angle, lamp, pressed=None, vu=0, vu_col=None):
        c = Canvas(32, 32)
        c.bevel(1, 3, 30, 28, P["m2"], P["m3"], P["m1"])
        c.hline(2, 29, 4, P["m4"])
        c.rect(3, 6, 26, 15, P["m1"])  # reel bay
        c.box(3, 6, 26, 15, P["m0"])
        draw_reel(c, 10, 13, 6.2, angle, 5.6)
        draw_reel(c, 22, 13, 6.2, angle + 23, 3.6)
        # tape path + head
        c.hline(8, 24, 20, P["tape"])
        c.rect(14, 18, 4, 3, P["m4"])
        c.p(15, 18, P["m5"])
        # status lamp + label
        c.rect(26, 1, 4, 3, P["ink"])
        c.rect(27, 1, 2, 2, lamp)
        c.p(27, 1, P["white"] if lamp not in (P["m2"], P["m3"]) else P["m4"])
        c.rect(3, 1, 9, 2, P["m1"])  # nameplate
        c.hline(4, 10, 1, P["a1"])
        # buttons: REC PLAY REW STOP
        btns = [P["r2"], P["g2"], P["a2"], P["m4"]]
        for i, col in enumerate(btns):
            bx = 4 + i * 6
            down = pressed == i
            c.rect(bx, 23 + (1 if down else 0), 5, 3 - (1 if down else 0), col if down else
                   tuple(int(v * 0.55) for v in col[:3]) + (255,))
            c.hline(bx, bx + 4, 26, P["ink"])
            if not down:
                c.hline(bx, bx + 4, 23, col)
        # VU meter
        for i in range(6):
            col = P["m0"]
            if i < vu:
                col = vu_col or (P["g2"] if i < 4 else P["a2"])
            c.p(28, 28 - i * 2 + 1, col)
            c.p(28, 28 - i * 2, col)
        c.vline(28, 18, 22, P["m0"])
        # feet
        c.rect(3, 31, 4, 1, P["ink"])
        c.rect(25, 31, 4, 1, P["ink"])
        c.outline()
        return c

    frames.append(deck(0, P["m3"]))  # 0 idle
    vus = [3, 5, 4, 6, 3, 4]
    for i in range(6):  # 1-6 rec
        frames.append(deck(i * 20, P["r2"] if i < 3 else P["r0"], 0, vus[i], P["r2"] if vus[i] > 4 else None))
    for i in range(6):  # 7-12 play
        frames.append(deck(i * 20, P["g3"], 1, vus[(i + 2) % 6]))
    for i in range(6):  # 13-18 rewind (fast, reverse)
        frames.append(deck(-i * 40, P["a2"], 2, 2))
    for i in range(2):  # 19-20 memory full
        frames.append(deck(0, P["r3"] if i == 0 else P["r0"], None, 6 if i == 0 else 0, P["r2"]))
    sheet = save_sheet(
        "Assets/Art/Objects/TapeRecorder/tape_recorder.png", frames, cols=7, pivot=(0.5, 0.0),
        group="TapeRecorder",
        animations=[
            ("TapeRecorder_Idle", [0], 1, True),
            ("TapeRecorder_Recording", [1, 2, 3, 4, 5, 6], 12, True),
            ("TapeRecorder_Playback", [7, 8, 9, 10, 11, 12], 12, True),
            ("TapeRecorder_Rewind", [13, 14, 15, 16, 17, 18], 18, True),
            ("TapeRecorder_MemoryFull", [19, 20], 4, True),
        ])
    mode_controller("TapeRecorder", sheet, [
        ("Idle", "TapeRecorder_Idle"), ("Recording", "TapeRecorder_Recording"),
        ("Playback", "TapeRecorder_Playback"), ("Rewind", "TapeRecorder_Rewind"),
        ("MemoryFull", "TapeRecorder_MemoryFull")], sorting=5)


def gen_door():
    frames = []
    shifts = [0, 7, 15, 23, 31, 38, 42]
    for i, s in enumerate(shifts):
        c = Canvas(16, 48)
        # panel (drawn first, clipped below header)
        panel = Canvas(12, 43)
        panel.rect(0, 0, 12, 43, P["m2"])
        panel.vline(0, 0, 42, P["m3"])
        panel.vline(11, 0, 42, P["m1"])
        for yy in range(6, 36, 7):
            panel.hline(1, 10, yy, P["m1"])
            panel.hline(1, 10, yy + 1, P["m3"])
        panel.rect(3, 9, 6, 4, P["ink"])  # small window
        panel.rect(4, 10, 4, 2, P["g0"])
        panel.p(4, 10, P["g1"])
        for x in range(12):
            for y in range(37, 42):
                panel.p(x, y, P["a2"] if ((x + y) // 2) % 2 == 0 else P["ink"])
        panel.hline(0, 11, 42, P["ink"])
        for y in range(43):
            for x in range(12):
                ty = 5 + y - s
                if 5 <= ty < 48:
                    c.p(2 + x, ty, panel.px[x, y])
        # frame/jambs
        c.rect(0, 0, 2, 48, P["m1"])
        c.rect(14, 0, 2, 48, P["m1"])
        c.vline(0, 0, 47, P["ink"])
        c.vline(15, 0, 47, P["ink"])
        c.vline(1, 5, 47, P["m3"])
        c.bevel(0, 0, 16, 5, P["m2"], P["m4"], P["ink"])
        lamp = P["r2"] if i == 0 else (P["g3"] if i == len(shifts) - 1 else P["a2"])
        c.rect(6, 1, 4, 2, lamp)
        c.p(6, 1, P["white"])
        c.hline(2, 13, 47, P["m0"])  # floor rail
        frames.append(c)
    outline_sheet(frames, "Assets/Art/Objects/Door/door_outline.png", "DoorOutline")
    last = len(frames) - 1
    sheet = save_sheet(
        "Assets/Art/Objects/Door/door.png", frames, cols=7, pivot=(0.5, 0.0), group="Door",
        animations=[
            ("Door_Closed", [0], 1, True),
            ("Door_Opening", list(range(last + 1)), 14, False),
            ("Door_Open", [last], 1, True),
            ("Door_Closing", list(range(last, -1, -1)), 14, False),
        ])
    controller(
        "Door", sheet, "Closed",
        [("Closed", "Door_Closed"), ("Opening", "Door_Opening"), ("Open", "Door_Open"),
         ("Closing", "Door_Closing")],
        params=[("IsOpen", "Bool")],
        transitions=[
            ("Closed", "Opening", False, [("IsOpen", "If", 0)]),
            ("Opening", "Open", True, []),
            ("Open", "Closing", False, [("IsOpen", "IfNot", 0)]),
            ("Closing", "Closed", True, []),
        ], sorting=2)


def gen_switch():
    frames = []
    for state in range(3):  # 0 off(up), 1 mid, 2 on(down)
        c = Canvas(16, 16)
        c.bevel(2, 2, 12, 12, P["m2"], P["m3"], P["m1"], edge=P["ink"])
        for x, y in ((3, 3), (12, 3), (3, 12), (12, 12)):
            c.p(x, y, P["m4"])
        c.rect(7, 4, 2, 8, P["ink"])
        ends = [(8, 1), (12, 7), (8, 14)]
        ex, ey = ends[state]
        c.line(8, 8, ex, ey, P["m5"])
        c.rect(ex - 1, ey - 1, 3, 2, P["a2"])
        c.p(ex - 1, ey - 1, P["a3"])
        lamp = [P["r2"], P["a2"], P["g3"]][state]
        c.p(11, 4, lamp)
        c.p(4, 10, P["g1"] if state == 2 else P["m1"])
        c.outline()
        frames.append(c)
    sheet = save_sheet(
        "Assets/Art/Objects/Switch/switch_lever.png", frames, pivot=(0.5, 0.5), group="Switch",
        animations=[
            ("Switch_Off", [0], 1, True), ("Switch_TurningOn", [0, 1, 2], 16, False),
            ("Switch_On", [2], 1, True), ("Switch_TurningOff", [2, 1, 0], 16, False),
        ])
    bool_toggle_controller("Switch", sheet, "Switch", "IsOn", sorting=3)

    # Power switch (breaker box)
    frames = []
    for state in range(3):
        c = Canvas(16, 24)
        c.rect(1, 2, 14, 20, P["m1"])
        for y in range(2, 22):
            for x in (1, 14):
                c.p(x, y, P["a2"] if (y // 2) % 2 == 0 else P["ink"])
        for x in range(1, 15):
            for y in (2, 21):
                c.p(x, y, P["a2"] if (x // 2) % 2 == 0 else P["ink"])
        c.rect(3, 4, 10, 16, P["m2"])
        # lightning bolt
        bolt = ["..##", ".##.", "####", ".##.", "##.."]
        c.ascii(6, 5, bolt, {"#": P["a2"] if state == 2 else P["a0"]})
        c.rect(7, 11, 2, 8, P["ink"])  # slot
        hy = [11, 14, 17][state]
        c.rect(4, hy, 8, 2, P["r2"] if state == 0 else (P["a2"] if state == 1 else P["g2"]))
        c.hline(4, 11, hy, P["white"])
        c.p(3, 19, P["g3"] if state == 2 else P["r1"])
        c.outline()
        frames.append(c)
    sheet = save_sheet(
        "Assets/Art/Objects/Switch/power_switch.png", frames, pivot=(0.5, 0.0), group="PowerSwitch",
        animations=[
            ("PowerSwitch_Off", [0], 1, True), ("PowerSwitch_TurningOn", [0, 1, 2], 12, False),
            ("PowerSwitch_On", [2], 1, True), ("PowerSwitch_TurningOff", [2, 1, 0], 12, False),
        ])
    bool_toggle_controller("PowerSwitch", sheet, "PowerSwitch", "IsOn", sorting=3)


def gen_platform():
    frames = []

    def plat(lit, col):
        c = Canvas(48, 10)
        c.rect(1, 1, 46, 6, P["m2"])
        c.hline(1, 46, 1, P["m5"])
        c.hline(1, 46, 2, P["m4"])
        c.hline(1, 46, 6, P["m1"])
        for x in list(range(1, 5)) + list(range(43, 47)):
            for y in range(3, 6):
                c.p(x, y, P["a2"] if ((x + y) // 2) % 2 == 0 else P["ink"])
        for i, lx in enumerate(range(9, 40, 7)):
            c.rect(lx, 4, 3, 1, col if lit == i else (P["m0"] if col is None else tuple(int(v * 0.35) for v in col[:3]) + (255,)))
            if lit == i:
                c.p(lx + 1, 3, P["white"])
        # underside thruster pods
        for px_ in (10, 34):
            c.rect(px_, 7, 4, 2, P["m1"])
            c.hline(px_ + 1, px_ + 2, 8, P["g1"] if lit is not None else P["m0"])
        c.outline()
        return c

    frames.append(plat(None, None))  # 0 inactive
    for col in (P["a2"], P["r2"], P["g3"]):
        for i in range(5):
            frames.append(plat(i, col))
    sheet = save_sheet(
        "Assets/Art/Objects/MovingPlatform/moving_platform.png", frames, cols=4, pivot=(0.5, 0.5),
        group="MovingPlatform",
        animations=[
            ("MovingPlatform_Inactive", [0], 1, True),
            ("MovingPlatform_Active", [1, 2, 3, 4, 5], 10, True),
            ("MovingPlatform_Recording", [6, 7, 8, 9, 10], 10, True),
            ("MovingPlatform_Playback", [11, 12, 13, 14, 15], 10, True),
        ])
    mode_controller("MovingPlatform", sheet, [
        ("Inactive", "MovingPlatform_Inactive"), ("Active", "MovingPlatform_Active"),
        ("Recording", "MovingPlatform_Recording"), ("Playback", "MovingPlatform_Playback")], sorting=1)


def gen_conveyor():
    frames = []
    for f in range(4):
        c = Canvas(48, 12)
        c.rect(3, 2, 42, 8, P["m1"])
        for x in range(3, 45):
            on = ((x + f) // 2) % 2 == 0
            c.p(x, 2, P["m4"] if on else P["m2"])
            c.p(x, 9, P["m2"] if on else P["m0"])
        for x in range(8, 41, 8):
            c.rect(x, 4, 3, 4, P["m2"])
            c.p(x + 1, 5, P["ink"])
        for cx in (5, 42):
            draw_reel(c, cx + 0.5, 6, 4.2, f * 30 if True else 0, 0, spokes=4)
        for x in (11, 36):
            c.p(x, 11, P["ink"])
        c.outline()
        frames.append(c)
    sheet = save_sheet(
        "Assets/Art/Objects/Conveyor/conveyor.png", frames, pivot=(0.5, 0.5), group="Conveyor",
        animations=[
            ("Conveyor_Off", [0], 1, True),
            ("Conveyor_Right", [3, 2, 1, 0], 12, True),
            ("Conveyor_Left", [0, 1, 2, 3], 12, True),
        ])
    mode_controller("Conveyor", sheet, [
        ("Off", "Conveyor_Off"), ("Right", "Conveyor_Right"), ("Left", "Conveyor_Left")], sorting=1)


def screen_text(c, x0, y0, w, h, scroll, col, dim, seed=3, cursor=True):
    rnd = random.Random(seed)
    lines = [rnd.randint(2, w - 2) for _ in range(40)]
    for row in range(0, h - 1, 2):
        idx = (row // 2 + scroll) % len(lines)
        ln = lines[idx]
        for x in range(ln):
            if rnd.random() > 0.15:
                c.p(x0 + 1 + x, y0 + 1 + row, col if x % 7 != 6 else dim)
    if cursor:
        c.rect(x0 + 1, y0 + h - 2, 2, 1, col)


def crt_scan(c, x0, y0, w, h):
    for y in range(y0, y0 + h):
        if (y - y0) % 2 == 1:
            for x in range(x0, x0 + w):
                p = c.px[x, y]
                c.px[x, y] = (int(p[0] * 0.75), int(p[1] * 0.75), int(p[2] * 0.75), p[3])


def gen_crt_monitor():
    frames = []

    def monitor(mode, f):
        c = Canvas(32, 32)
        c.bevel(2, 2, 28, 22, P["m2"], P["m3"], P["m1"])
        c.rect(24, 4, 5, 18, P["m1"])  # side panel
        c.p(26, 6, P["rust2"])
        c.rect(25, 9, 3, 3, P["m3"])
        c.p(26, 10, P["ink"])
        c.rect(25, 14, 3, 3, P["m3"])
        c.p(26, 16, P["ink"])
        c.p(26, 19, P["g3"] if mode != "off" else P["g0"])
        sx, sy, sw, sh = 4, 4, 19, 17
        base = {"idle": P["g0"], "error": P["r0"], "off": P["m0"]}[mode]
        c.rect(sx, sy, sw, sh, base)
        if mode == "idle":
            screen_text(c, sx, sy, sw, sh, f * 2, P["g3"], P["g2"], cursor=f % 2 == 0)
            if f == 3:  # flicker frame
                for x in range(sx, sx + sw):
                    c.p(x, sy + 7, P["g1"])
        elif mode == "error":
            if f == 0:
                draw_glyph(c, sx + 7, sy + 5, "!", P["r3"])
                c.box(sx + 2, sy + 2, sw - 4, sh - 4, P["r2"])
        else:
            c.p(sx + 3, sy + 2, P["m2"])
            c.p(sx + 4, sy + 2, P["m1"])
        crt_scan(c, sx, sy, sw, sh)
        # rounded screen corners
        for (x, y) in ((sx, sy), (sx + sw - 1, sy), (sx, sy + sh - 1), (sx + sw - 1, sy + sh - 1)):
            c.p(x, y, P["m1"])
        if mode != "off":
            c.p(sx + 1, sy + 1, P["g4"] if mode == "idle" else P["r3"])
        # stand + base box
        c.rect(12, 24, 8, 2, P["m1"])
        c.bevel(5, 26, 22, 5, P["rust1"], P["rust2"], P["rust0"])
        for x in range(8, 24, 3):
            c.vline(x, 27, 29, P["rust0"])
        c.outline()
        return c

    for f in range(4):
        frames.append(monitor("idle", f))
    for f in range(2):
        frames.append(monitor("error", f))
    frames.append(monitor("off", 0))
    outline_sheet(frames, "Assets/Art/Objects/CRTMonitor/crt_monitor_outline.png", "CRTMonitorOutline")
    sheet = save_sheet(
        "Assets/Art/Objects/CRTMonitor/crt_monitor.png", frames, pivot=(0.5, 0.0), group="CRTMonitor",
        animations=[
            ("CRTMonitor_On", [0, 1, 2, 0, 1, 3], 4, True),
            ("CRTMonitor_Error", [4, 5], 4, True),
            ("CRTMonitor_Off", [6], 1, True),
        ])
    mode_controller("CRTMonitor", sheet, [
        ("On", "CRTMonitor_On"), ("Error", "CRTMonitor_Error"), ("Off", "CRTMonitor_Off")], sorting=1)


def outline_sheet(frames, rel_path, group, margin=2):
    """Hover-highlight ring around the union silhouette of all frames (amber, 2px).
    Pivot is placed so it lines up with a bottom-centre pivoted source sprite."""
    w, h = frames[0].w, frames[0].h
    solid = [[any(f.px[x, y][3] > 0 for f in frames) for x in range(w)] for y in range(h)]
    c = Canvas(w + margin * 2, h + margin * 2)
    for y in range(c.h):
        for x in range(c.w):
            sx, sy = x - margin, y - margin
            if 0 <= sx < w and 0 <= sy < h and solid[sy][sx]:
                continue
            d = None
            for r in range(1, margin + 1):
                if any(0 <= sx + dx < w and 0 <= sy + dy < h and solid[sy + dy][sx + dx]
                       for dx in range(-r, r + 1) for dy in range(-r, r + 1)):
                    d = r
                    break
            if d == 1:
                c.p(x, y, P["a3"])
            elif d == 2:
                c.p(x, y, with_alpha(P["a2"], 200))
    save_sheet(rel_path, [c], pivot=(0.5, margin / c.h), group=group)


def gen_main_terminal():
    frames = []

    def term(mode, f):
        rnd = random.Random(f * 7 + 1)
        c = Canvas(48, 40)
        # side cabinets with LEDs
        for cx in (1, 37):
            c.bevel(cx, 8, 10, 31, P["m1"], P["m2"], P["m0"])
            for yy in range(11, 22, 3):
                for xx in range(cx + 2, cx + 8, 2):
                    on = rnd.random() < 0.5 and mode != "off"
                    col = P["g2"] if on else P["m0"]
                    if on and rnd.random() < 0.2:
                        col = P["a2"]
                    c.p(xx, yy, col)
            draw_reel(c, cx + 5, 30, 3.6, f * 30 if mode in ("active", "glitch") else 0, 2.6)
        # central monitor
        c.bevel(10, 1, 28, 24, P["m2"], P["m4"], P["m1"])
        sx, sy, sw, sh = 12, 3, 24, 18
        base = {"off": P["m0"], "locked": P["a0"], "active": P["g0"], "glitch": P["g0"]}[mode]
        c.rect(sx, sy, sw, sh, base)
        if mode == "locked":
            draw_text(c, sx + 2, sy + 3, "[", P["a2"])
            c.rect(sx + 9, sy + 6, 6, 5, P["a2"])  # padlock body
            c.box(sx + 10, sy + 3, 4, 4, P["a2"])
            c.p(sx + 11, sy + 8, P["a0"])
            draw_text(c, sx + 17, sy + 3, "]", P["a2"])
            if f == 0:
                c.rect(sx + 2, sy + sh - 3, 3, 1, P["a2"])
        elif mode == "active":
            screen_text(c, sx, sy, sw, sh, f * 2, P["g3"], P["g2"], seed=9, cursor=f % 2 == 0)
        elif mode == "glitch":
            screen_text(c, sx, sy, sw, sh, f * 5, P["g3"], P["g2"], seed=11)
            for _ in range(5):
                y = rnd.randrange(sy, sy + sh)
                col = rnd.choice([P["white"], P["r2"], P["g4"], P["a2"]])
                x0 = rnd.randrange(sx, sx + sw - 4)
                c.hline(x0, min(sx + sw - 1, x0 + rnd.randint(4, 14)), y, col)
        if mode != "off":
            crt_scan(c, sx, sy, sw, sh)
        # desk + keyboard
        c.bevel(9, 25, 30, 4, P["rust1"], P["rust2"], P["rust0"])
        c.rect(11, 26, 26, 2, P["m1"])
        for x in range(12, 36, 2):
            c.p(x, 26, P["m3"])
            c.p(x + 1, 27, P["m3"])
        c.rect(12, 29, 24, 10, P["m1"])
        c.vline(12, 29, 38, P["m2"])
        c.rect(22, 31, 4, 2, P["g3"] if mode in ("active", "glitch") else (P["a2"] if mode == "locked" else P["m0"]))
        c.outline()
        return c

    frames.append(term("off", 0))  # 0
    frames += [term("locked", f) for f in range(2)]  # 1-2
    frames += [term("active", f) for f in range(4)]  # 3-6
    frames += [term("glitch", f) for f in range(4)]  # 7-10
    sheet = save_sheet(
        "Assets/Art/Objects/Terminal/main_terminal.png", frames, cols=6, pivot=(0.5, 0.0),
        group="MainTerminal",
        animations=[
            ("MainTerminal_Off", [0], 1, True),
            ("MainTerminal_Locked", [1, 2], 3, True),
            ("MainTerminal_Active", [3, 4, 5, 6], 5, True),
            ("MainTerminal_Glitch", [7, 8, 9, 10, 8, 7], 14, True),
        ])
    outline_sheet(frames, "Assets/Art/Objects/Terminal/main_terminal_outline.png", "MainTerminalOutline")
    mode_controller("MainTerminal", sheet, [
        ("Off", "MainTerminal_Off"), ("Locked", "MainTerminal_Locked"),
        ("Active", "MainTerminal_Active"), ("Glitch", "MainTerminal_Glitch")], sorting=1)

    # Exit terminal (pillar)
    frames = []
    for unlocked in (False, True):
        for f in range(2):
            c = Canvas(16, 32)
            c.bevel(2, 4, 12, 27, P["m2"], P["m3"], P["m1"])
            c.rect(4, 7, 8, 7, P["g0"] if unlocked else P["r0"])
            if unlocked:
                if f == 0:
                    draw_glyph(c, 6, 7, ">", P["g3"])
            else:
                c.line(5, 8, 10, 12, P["r2"])
                c.line(10, 8, 5, 12, P["r2"])
            crt_scan(c, 4, 7, 8, 7)
            # big beacon
            lit = unlocked or f == 0
            col = (P["g3"] if unlocked else P["r2"]) if lit else (P["g1"] if unlocked else P["r1"])
            c.rect(5, 0, 6, 4, col)
            c.hline(5, 10, 0, P["white"] if lit else col)
            c.rect(4, 3, 8, 1, P["m1"])
            for y in range(17, 28, 3):
                c.hline(4, 11, y, P["m1"])
            c.rect(6, 15, 4, 1, P["a2"])
            c.outline()
            frames.append(c)
    outline_sheet(frames, "Assets/Art/Objects/Terminal/exit_terminal_outline.png", "ExitTerminalOutline")
    sheet = save_sheet(
        "Assets/Art/Objects/Terminal/exit_terminal.png", frames, pivot=(0.5, 0.0), group="ExitTerminal",
        animations=[
            ("ExitTerminal_Locked", [0, 1], 2, True),
            ("ExitTerminal_Unlocked", [2, 3], 4, True),
        ])
    controller(
        "ExitTerminal", sheet, "Locked",
        [("Locked", "ExitTerminal_Locked"), ("Unlocked", "ExitTerminal_Unlocked")],
        params=[("IsUnlocked", "Bool")],
        transitions=[
            ("Locked", "Unlocked", False, [("IsUnlocked", "If", 0)]),
            ("Unlocked", "Locked", False, [("IsUnlocked", "IfNot", 0)]),
        ], sorting=1)


def gen_main_computer():
    """The big central console of the Control Room (96x64): monitor, tape tower, LED/VU tower, desk."""
    def big(mode, f):
        rnd = random.Random(f * 31 + {"off": 0, "locked": 1, "active": 2, "glitch": 3}[mode] * 7)
        on = mode != "off"
        running = mode in ("active", "glitch")
        c = Canvas(96, 64)
        # cables drooping between towers and monitor
        for x0, x1, col, dy in ((18, 30, P["ink"], 0), (66, 80, P["r1"], 0), (16, 28, P["g1"], 2)):
            for t in range(21):
                x = x0 + (x1 - x0) * t / 20
                c.p(x, 6 + 5 * math.sin(math.pi * t / 20) + dy, col)
        # left tape tower
        c.bevel(1, 8, 20, 40, P["m2"], P["m3"], P["m1"])
        c.rect(3, 10, 16, 30, P["m1"])
        spin = f * 30 if running else 0
        draw_reel(c, 11, 17, 6.4, spin, 5.4)
        draw_reel(c, 11, 32, 6.4, spin + 40, 3.2)
        c.vline(4, 17, 32, P["tape"])
        c.rect(4, 42, 14, 3, P["m0"])
        for i in range(7):
            c.p(5 + i * 2, 43, P["g3"] if (on and rnd.random() < 0.6) else P["m0"])
        # right tower: LED matrix + two VU meters + toggles
        c.bevel(75, 8, 20, 40, P["m2"], P["m3"], P["m1"])
        c.rect(77, 10, 16, 11, P["ink"])
        for yy in range(5):
            for xx in range(7):
                col = P["m0"]
                if on:
                    r = rnd.random()
                    if mode == "locked":
                        col = P["a1"] if r < 0.3 else P["m0"]
                    else:
                        col = P["g2"] if r < 0.45 else (P["a2"] if r < 0.55 else (P["r2"] if r < 0.58 else P["m0"]))
                c.p(78 + xx * 2, 11 + yy * 2, col)
        for vy in (24, 33):
            c.rect(78, vy, 14, 7, P["paper"] if on else P["paper2"])
            c.box(77, vy - 1, 16, 9, P["ink"])
            a = math.radians(200 + (rnd.uniform(20, 140) if running else 25))
            c.line(85, vy + 6, 85 + math.cos(a) * 5, vy + 6 + math.sin(a) * 5, P["r1"])
        for i in range(4):
            c.rect(78 + i * 4, 43, 2, 3, P["m4"])
            c.p(78 + i * 4, 43 if (running and (i + f) % 2) else 45, P["white"])
        # monitor
        c.bevel(22, 1, 52, 42, P["m2"], P["m4"], P["m1"])
        c.hline(23, 72, 2, P["m3"])
        for x in range(40, 56, 2):
            c.vline(x, 3, 4, P["m1"])
        sx, sy, sw, sh = 27, 6, 42, 29
        base = {"off": P["m0"], "locked": P["a0"], "active": P["g0"], "glitch": P["g0"]}[mode]
        c.rect(sx, sy, sw, sh, base)
        if mode == "locked":
            c.box(sx + 16, sy + 3, 10, 8, P["a2"])
            c.box(sx + 17, sy + 4, 8, 7, P["a0"])
            c.rect(sx + 13, sy + 9, 16, 10, P["a2"])
            c.rect(sx + 20, sy + 12, 2, 4, P["a0"])
            draw_text(c, sx + 3, sy + 21, "LOCKED", P["a2"] if f == 0 else P["a1"])
        elif mode == "active":
            screen_text(c, sx, sy, sw, sh, f * 2, P["g3"], P["g2"], seed=21, cursor=f % 2 == 0)
        elif mode == "glitch":
            screen_text(c, sx, sy, sw, sh, f * 5, P["g3"], P["g2"], seed=23)
            for _ in range(7):
                y = rnd.randrange(sy, sy + sh)
                x0 = rnd.randrange(sx, sx + sw - 6)
                c.hline(x0, min(sx + sw - 1, x0 + rnd.randint(6, 24)), y,
                        rnd.choice([P["white"], P["r2"], P["g4"], P["a2"]]))
        else:
            c.p(sx + 4, sy + 3, P["m2"])
            c.p(sx + 5, sy + 3, P["m1"])
            c.p(sx + 4, sy + 4, P["m1"])
        if on:
            crt_scan(c, sx, sy, sw, sh)
            c.p(sx + 1, sy + 1, P["g4"] if mode != "locked" else P["a3"])
        for (x, y) in ((sx, sy), (sx + sw - 1, sy), (sx, sy + sh - 1), (sx + sw - 1, sy + sh - 1)):
            c.p(x, y, P["m1"])
        c.rect(30, 37, 20, 3, P["a1"])
        c.hline(31, 48, 38, P["a0"])
        c.p(66, 38, P["g3"] if on else P["g0"])
        c.rect(58, 37, 3, 3, P["m4"])
        c.rect(62, 37, 3, 3, P["m4"])
        # desk / console
        c.bevel(0, 43, 96, 4, P["rust1"], P["rust2"], P["rust0"])
        c.rect(26, 44, 44, 2, P["m1"])
        for x in range(27, 69, 2):
            c.p(x, 44, P["m3"])
            c.p(x + 1, 45, P["m3"])
        c.bevel(2, 47, 92, 15, P["m1"], P["m2"], P["m0"])
        for x in list(range(6, 24, 3)) + list(range(72, 90, 3)):
            c.vline(x, 50, 58, P["m0"])
        btn = [P["r2"], P["g2"], P["a2"], P["m4"]]
        for i, col in enumerate(btn):
            lit = (running and i == 1) or (mode == "locked" and i == 2 and f == 0)
            c.rect(34 + i * 7, 51, 5, 3, col if lit else tuple(int(v * 0.5) for v in col[:3]) + (255,))
        for x in range(30, 66):
            c.p(x, 58, P["a2"] if (x // 2) % 2 == 0 else P["ink"])
        c.rect(4, 62, 6, 2, P["ink"])
        c.rect(86, 62, 6, 2, P["ink"])
        c.outline()
        return c

    frames = [big("off", 0)] + [big("locked", f) for f in range(2)] + \
             [big("active", f) for f in range(4)] + [big("glitch", f) for f in range(4)]
    sheet = save_sheet("Assets/Art/Objects/Terminal/main_computer.png", frames, cols=4, pivot=(0.5, 0.0),
                       group="MainComputer",
                       animations=[("MainComputer_Off", [0], 1, True),
                                   ("MainComputer_Locked", [1, 2], 2, True),
                                   ("MainComputer_Active", [3, 4, 5, 6], 5, True),
                                   ("MainComputer_Glitch", [7, 8, 9, 10, 8, 7], 14, True)])
    outline_sheet(frames, "Assets/Art/Objects/Terminal/main_computer_outline.png", "MainComputerOutline")
    mode_controller("MainComputer", sheet, [
        ("Off", "MainComputer_Off"), ("Locked", "MainComputer_Locked"),
        ("Active", "MainComputer_Active"), ("Glitch", "MainComputer_Glitch")], sorting=1)


def gen_small_terminal():
    """A simple box terminal (32x24) for the side rooms."""
    def st(mode, f):
        c = Canvas(32, 24)
        c.bevel(6, 0, 20, 16, P["m2"], P["m4"], P["m1"])
        sx, sy, sw, sh = 8, 2, 16, 11
        base = {"off": P["m0"], "standby": P["g0"], "active": P["g0"], "error": P["r0"]}[mode]
        c.rect(sx, sy, sw, sh, base)
        if mode == "standby":
            c.p(sx + 1, sy + 1, P["g2"])
            c.p(sx + 2, sy + 1, P["g2"])
            if f == 0:
                c.rect(sx + 4, sy + 1, 2, 2, P["g3"])
        elif mode == "active":
            screen_text(c, sx, sy, sw, sh, f * 2, P["g3"], P["g2"], seed=5, cursor=f % 2 == 0)
        elif mode == "error" and f == 0:
            draw_glyph(c, sx + 6, sy + 2, "!", P["r3"])
        if mode != "off":
            crt_scan(c, sx, sy, sw, sh)
        for (x, y) in ((sx, sy), (sx + sw - 1, sy), (sx, sy + sh - 1), (sx + sw - 1, sy + sh - 1)):
            c.p(x, y, P["m1"])
        led = {"off": P["m0"], "standby": P["a2"], "active": P["g3"], "error": P["r2"]}[mode]
        c.p(23, 14, led)
        c.rect(13, 16, 6, 2, P["m1"])
        c.rect(2, 19, 28, 3, P["m2"])
        c.hline(2, 29, 18, P["m3"])
        for x in range(3, 29, 2):
            c.p(x, 19, P["m1"])
            c.p(x + 1, 20, P["m1"])
        c.hline(2, 29, 22, P["m0"])
        c.outline()
        return c

    frames = [st("off", 0)] + [st("standby", f) for f in range(2)] + \
             [st("active", f) for f in range(4)] + [st("error", f) for f in range(2)]
    sheet = save_sheet("Assets/Art/Objects/Terminal/small_terminal.png", frames, cols=5, pivot=(0.5, 0.0),
                       group="SmallTerminal",
                       animations=[("SmallTerminal_Off", [0], 1, True),
                                   ("SmallTerminal_Standby", [1, 2], 2, True),
                                   ("SmallTerminal_Active", [3, 4, 5, 6], 5, True),
                                   ("SmallTerminal_Error", [7, 8], 4, True)])
    outline_sheet(frames, "Assets/Art/Objects/Terminal/small_terminal_outline.png", "SmallTerminalOutline")
    mode_controller("SmallTerminal", sheet, [
        ("Off", "SmallTerminal_Off"), ("Standby", "SmallTerminal_Standby"),
        ("Active", "SmallTerminal_Active"), ("Error", "SmallTerminal_Error")], sorting=1)


# ==========================================================================
# INTRO CUTSCENE ART
# ==========================================================================
def gen_intro_art():
    W, H = 320, 180
    rnd = random.Random(707)

    # ---- dusk sky (camera-fixed background)
    sky = Canvas(W, H)
    stops = [(0, hexc("080B14")), (70, hexc("161B30")), (112, hexc("3A2836")), (128, hexc("7A4A32")), (140, hexc("2A1E22")), (180, hexc("0E1014"))]
    for y in range(H):
        for (y0, c0), (y1, c1) in zip(stops, stops[1:]):
            if y0 <= y <= y1:
                t = (y - y0) / max(1, y1 - y0)
                sky.hline(0, W - 1, y, tuple(int(c0[i] * (1 - t) + c1[i] * t) for i in range(3)) + (255,))
                break
    for _ in range(90):  # stars
        x, y = rnd.randrange(W), rnd.randrange(0, 95)
        sky.p(x, y, rnd.choice([hexc("5A6478"), hexc("8A94A8"), hexc("C8D0E0")]))
    _glow(sky, 252, 34, 40, hexc("C8D0E0"), 0.18)
    sky.disc(252, 34, 9, hexc("D8D4C4"))  # moon
    for cx, cy, r in ((249, 31, 2), (256, 37, 1.6), (251, 39, 1.2)):
        sky.disc(cx, cy, r, hexc("B8B2A2"))
    # ruined city skyline on the horizon
    x = 0
    while x < W:
        w = rnd.randint(6, 18)
        h = rnd.randint(8, 34)
        top = 132 - h
        col = hexc("15151E")
        sky.rect(x, top, w, 132 - top, col)
        if rnd.random() < 0.5:  # broken top
            for i in range(w // 2):
                sky.p(x + i * 2, top - rnd.randint(0, 3), col)
        for _ in range(rnd.randint(0, 3)):
            sky.p(x + rnd.randrange(w), top + rnd.randrange(max(1, h - 2)), hexc("6A4A22"))
        x += w + rnd.randint(1, 8)
    # power pylons with sagging wires
    pylons = (40, 140, 240, 340)
    for px in pylons:
        sky.line(px - 5, 136, px, 96, hexc("101018"))
        sky.line(px + 5, 136, px, 96, hexc("101018"))
        sky.hline(px - 8, px + 8, 102, hexc("101018"))
        sky.hline(px - 6, px + 6, 110, hexc("101018"))
    for a, b in zip(pylons, pylons[1:]):
        for t in range(0, 101):
            xx = a + (b - a) * t / 100
            sky.p(xx, 102 + 10 * math.sin(math.pi * t / 100), hexc("0C0C12"))
    # hills
    for x in range(W):
        h1 = 140 + 5 * math.sin(x / 37) + 3 * math.sin(x / 13 + 1)
        sky.vline(x, int(h1), H - 1, hexc("12141A"))
    save_sheet("Assets/Art/Intro/bg_exterior.png", [sky], pivot=(0.5, 0.5), group="Intro")

    # ---- ground strip (640 x 56) - surface line at y=8
    GW, GH = 640, 56
    g = Canvas(GW, GH)
    for x in range(GW):
        top = 8 + int(1.5 * math.sin(x / 9) + 1.0 * math.sin(x / 23 + 2))
        g.vline(x, top, GH - 1, hexc("241C18"))
        g.p(x, top, hexc("4E3C2E"))
        g.p(x, top + 1, hexc("3A2E26"))
        for y in range(top + 3, GH, 7):
            if rnd.random() < 0.25:
                g.p(x, y + rnd.randint(0, 3), hexc("1A1412"))
    for _ in range(60):  # rocks
        rx, ry = rnd.randrange(GW), rnd.randint(10, GH - 4)
        r = rnd.uniform(1, 3)
        g.disc(rx, ry, r, P["m1"])
        g.p(rx - 1, ry - 1, P["m2"])
    for _ in range(45):  # dead grass tufts
        gx = rnd.randrange(GW)
        top = 8 + int(1.5 * math.sin(gx / 9) + 1.0 * math.sin(gx / 23 + 2))
        for k in range(rnd.randint(2, 4)):
            g.line(gx + k, top, gx + k + rnd.randint(-1, 1), top - rnd.randint(2, 5), hexc("4A452A"))
    # debris: rusted barrel and a broken pipe
    for bx in (120, 470):
        g.rect(bx, 0, 8, 9, P["rust1"])
        g.hline(bx, bx + 7, 3, P["rust0"])
        g.vline(bx, 0, 8, P["rust2"])
    g.rect(300, 4, 22, 4, P["m2"])
    g.hline(300, 321, 4, P["m3"])
    g.outline()
    save_sheet("Assets/Art/Intro/exterior_ground.png", [g], pivot=(0.0, (GH - 8) / GH), group="Intro")

    # ---- bunker entrance (160 x 112), 2 frames (antenna light blink)
    def bunker(blink, online=False):
        c = Canvas(160, 112)
        # earth mound
        for x in range(160):
            h = int(46 * math.sin(math.pi * x / 159) ** 0.6)
            c.vline(x, 112 - 18 - h, 111, hexc("2A221E"))
            c.p(x, 112 - 18 - h, hexc("4A452A"))
            if x % 5 == 0:
                c.p(x, 112 - 17 - h, hexc("3A3622"))
        # concrete portal
        c.rect(40, 30, 80, 82, hexc("4A4A48"))
        c.rect(40, 30, 80, 3, hexc("6A6A66"))
        c.vline(40, 30, 111, hexc("6A6A66"))
        c.vline(119, 30, 111, hexc("2A2A28"))
        for _ in range(70):  # stains / cracks
            c.p(rnd.randint(41, 118), rnd.randint(34, 110), rnd.choice([hexc("3A3A38"), hexc("555550"), P["rust0"]]))
        c.line(48, 34, 54, 46, hexc("2A2A28"))
        c.line(54, 46, 52, 54, hexc("2A2A28"))
        # hazard frame around the door hole (door is 48 x 56 at x 56..103, y 56..111)
        for x in range(52, 108):
            for y in range(52, 112):
                if 56 <= x < 104 and y >= 56:
                    continue
                c.p(x, y, P["a2"] if ((x + y) // 4) % 2 == 0 else P["ink"])
        c.rect(56, 56, 48, 56, hexc("140808"))  # dark hole behind the door
        # sign plate
        c.rect(46, 38, 68, 11, P["m1"])
        c.box(46, 38, 68, 11, P["ink"])
        draw_text(c, 50, 40, "COMPLEX 07", P["a2"])
        # lamps either side
        for lx in (46, 110):
            c.rect(lx, 58, 4, 4, P["m2"])
            c.rect(lx + 1, 59, 2, 2, (P["g3"] if online else P["a3"]) if not blink else (P["g2"] if online else P["a2"]))
        # vent + pipes out of the hill
        c.rect(14, 74, 18, 8, P["m1"])
        for x in range(15, 31, 2):
            c.vline(x, 75, 80, P["ink"])
        c.rect(126, 70, 26, 4, P["m2"])
        c.hline(126, 151, 70, P["m3"])
        c.rect(148, 70, 4, 24, P["m2"])
        # antenna mast with blinking light
        c.vline(132, 4, 40, P["m2"])
        c.vline(133, 4, 40, P["m1"])
        for y in range(10, 40, 6):
            c.line(129, y, 136, y + 4, P["m1"])
        c.rect(131, 1, 4, 3, (P["g4"] if online else P["r3"]) if blink else (P["g1"] if online else P["r1"]))
        c.outline()
        if blink:
            for dx, dy in ((-2, 0), (5, 0), (1, -2)):
                c.p(131 + dx, 2 + dy, with_alpha(P["g3"] if online else P["r2"], 140))
        return c

    bsheet = save_sheet("Assets/Art/Intro/bunker.png",
                        [bunker(False), bunker(True), bunker(False, True), bunker(True, True)],
                        pivot=(0.5, 0.0), group="Intro",
                        animations=[("Bunker_Idle", [0, 0, 0, 1], 3, True), ("Bunker_Online", [2, 2, 2, 3], 3, True)])
    mode_controller("Bunker", bsheet, [("Idle", "Bunker_Idle"), ("Online", "Bunker_Online")])

    # ---- blast door (48 x 56), 8 frames: halves slide apart revealing red-lit corridor
    frames = []
    for f in range(8):
        c = Canvas(48, 56)
        # corridor behind
        for y in range(56):
            for x in range(48):
                d = abs(x - 24) / 24
                col = tuple(int(P["r0"][i] * (1 - d * 0.6) + P["ink"][i] * d * 0.6) for i in range(3)) + (255,)
                c.p(x, y, col)
        c.rect(18, 10, 12, 46, hexc("200A0C"))
        c.hline(0, 47, 6, P["r2"])  # red strip light
        open_px = int(24 * (f / 7) ** 1.2)
        for side in (0, 1):
            half = Canvas(24, 56, P["m2"])
            half.vline(0 if side == 0 else 23, 0, 55, P["m1"])
            for y in range(4, 52, 12):
                half.hline(1, 22, y, P["m1"])
                half.hline(1, 22, y + 1, P["m3"])
            for y in range(44, 52):
                for x in range(24):
                    half.p(x, y, P["a2"] if ((x + y + side * 3) // 3) % 2 == 0 else P["ink"])
            for (bx, by) in ((3, 3), (20, 3), (3, 40), (20, 40)):
                half.p(bx, by, P["m4"])
            if side == 0:
                half.rect(18, 22, 4, 10, P["m1"])  # handle
            else:
                half.vline(0, 0, 55, P["ink"])
            ox = (0 - open_px) if side == 0 else (24 + open_px)
            for y in range(56):
                for x in range(24):
                    tx = ox + x
                    if 0 <= tx < 48:
                        c.p(tx, y, half.px[x, y])
        frames.append(c)
    sheet = save_sheet("Assets/Art/Intro/blast_door.png", frames, pivot=(0.5, 0.0), group="BlastDoor",
                       animations=[("BlastDoor_Closed", [0], 1, True),
                                   ("BlastDoor_Opening", list(range(8)), 6, False),
                                   ("BlastDoor_Open", [7], 1, True)])
    controller("BlastDoor", sheet, "Closed",
               [("Closed", "BlastDoor_Closed"), ("Opening", "BlastDoor_Opening"), ("Open", "BlastDoor_Open")],
               params=[("IsOpen", "Bool")],
               transitions=[("Closed", "Opening", False, [("IsOpen", "If", 0)]),
                            ("Opening", "Open", True, [])], sorting=3)

    # ---- dialog portraits (48 x 48): operator + system
    def portrait_bg(c, tint):
        c.rect(0, 0, 48, 48, tint)
        for y in range(1, 48, 2):
            c.hline(0, 47, y, tuple(int(v * 0.8) for v in tint[:3]) + (255,))

    def operator_face(expr):
        c = Canvas(48, 48)
        portrait_bg(c, hexc("10201A"))
        # jumpsuit collar + shoulders
        c.rect(6, 40, 36, 8, P["suit1"])
        c.rect(6, 40, 4, 8, P["suit0"])
        c.line(18, 40, 24, 46, P["suit0"])
        c.line(30, 40, 24, 46, P["suit0"])
        c.rect(19, 35, 10, 6, P["skin2"])  # neck
        # head
        for y in range(10, 38):
            for x in range(12, 36):
                if ((x - 24) / 11.5) ** 2 + ((y - 24) / 13.5) ** 2 <= 1:
                    c.p(x, y, P["skin"] if x < 30 else P["skin2"])
        # hair
        for y in range(7, 20):
            for x in range(11, 37):
                if ((x - 24) / 13) ** 2 + ((y - 17) / 10) ** 2 <= 1 and (y < 15 or x < 15 or x > 33):
                    c.p(x, y, P["hair"])
        for x in range(13, 35, 3):
            c.p(x, 15 + (x % 2), P["hair"])
            c.p(x + 1, 16, P["hair"])
        # eyes / brows
        eye_y = 24
        for ex in (18, 28):
            if expr == "blink":
                c.hline(ex - 1, ex + 1, eye_y + 1, P["ink"])
            else:
                h = 3 if expr == "surprised" else 2
                c.rect(ex - 1, eye_y, 3, h, P["ink"])
                c.p(ex, eye_y, P["white"])
            c.hline(ex - 2, ex + 2, eye_y - 3 - (1 if expr == "surprised" else 0), P["hair"])
        c.vline(24, 26, 29, P["skin2"])  # nose
        c.p(25, 29, P["skin2"])
        if expr == "talk":
            c.rect(21, 32, 6, 2, P["ink"])
            c.hline(22, 25, 33, P["r1"])
        elif expr == "surprised":
            c.rect(22, 31, 4, 3, P["ink"])
        else:
            c.hline(21, 26, 32, P["skin2"])
        # headset: cup, band, mic boom, LED
        c.rect(9, 20, 5, 9, P["m2"])
        c.vline(9, 20, 28, P["m3"])
        c.line(11, 20, 15, 9, P["m1"])
        c.line(12, 28, 20, 33, P["m1"])
        c.rect(20, 32, 2, 2, P["m3"])
        c.p(11, 23, P["g3"])
        return c

    op = [operator_face(e) for e in ("neutral", "talk", "blink", "surprised")]
    save_sheet("Assets/Art/Intro/portrait_operator.png", op, pivot=(0.5, 0.5), group="Portraits")

    def system_face(mode):
        c = Canvas(48, 48)
        portrait_bg(c, hexc("0C1410"))
        c.bevel(4, 4, 40, 34, P["m2"], P["m4"], P["m1"])
        c.rect(8, 8, 32, 25, P["g0"])
        col = P["g3"]
        if mode == "glitch":
            col = P["r3"]
        if mode == "blink":
            c.hline(13, 18, 17, col)
            c.hline(29, 34, 17, col)
        else:
            c.rect(14, 14, 4, 5, col)
            c.rect(30, 14, 4, 5, col)
        if mode == "talk":
            for i, x in enumerate(range(15, 33, 2)):
                c.vline(x, 25 - (i % 3), 26 + (i % 3), col)
        else:
            c.hline(16, 31, 26, col)
        crt_scan(c, 8, 8, 32, 25)
        if mode == "glitch":
            src = c.im.copy().load()
            for y in (12, 13, 20, 26, 27):
                for x in range(8, 40):
                    c.px[x, y] = src[min(39, x + 3), y]
            c.hline(8, 39, 22, P["white"])
        c.rect(18, 38, 12, 4, P["m1"])
        c.rect(10, 42, 28, 4, P["m2"])
        c.p(38, 34, P["g3"])
        return c

    sysf = [system_face(m) for m in ("idle", "talk", "blink", "glitch")]
    save_sheet("Assets/Art/Intro/portrait_system.png", sysf, pivot=(0.5, 0.5), group="Portraits")

    # ---- red emergency light overlay (radial, transparent centre)
    e = Canvas(W, H)
    for y in range(H):
        for x in range(W):
            d = math.hypot((x - W / 2) / (W / 2), (y - 20) / H)
            a = int(min(1.0, d * 0.75) * 120)
            e.p(x, y, (110, 16, 22, a))
    save_sheet("Assets/Art/Intro/emergency_light.png", [e], pivot=(0.5, 0.5), group="Intro")


# ==========================================================================
# ENDING CUTSCENE ART
# ==========================================================================
def _vnoise(x, y, seed=0):
    """Smooth value noise in [0, 1]."""
    def h(ix, iy):
        n = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
        n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
        return (n & 0xFFFF) / 65535.0
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b, c, d = h(ix, iy), h(ix + 1, iy), h(ix, iy + 1), h(ix + 1, iy + 1)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _fbm(x, y, seed=0):
    return 0.6 * _vnoise(x, y, seed) + 0.3 * _vnoise(x * 2.1, y * 2.1, seed + 1) + 0.1 * _vnoise(x * 4.3, y * 4.3, seed + 2)


def _heat(v):
    """Heat (0..1) -> explosion palette: smoke -> red -> orange -> yellow -> white."""
    ramp = [(0.0, hexc("1C1816")), (0.12, hexc("2E2622")), (0.25, hexc("4A3A30")), (0.38, P["rust1"]),
            (0.5, P["r2"]), (0.62, P["rust2"]), (0.72, P["a2"]), (0.85, P["a3"]), (1.0, hexc("FFF8E8"))]
    for (v0, c0), (v1, c1) in zip(ramp, ramp[1:]):
        if v <= v1:
            t = (v - v0) / (v1 - v0)
            return tuple(int(c0[i] * (1 - t) + c1[i] * t) for i in range(3)) + (255,)
    return ramp[-1][1]


def gen_ending_art():
    # ---- nuclear explosion (128 x 128, 14 frames, pivot bottom-centre)
    N, S = 14, 128
    frames = []
    for f in range(N):
        p = f / (N - 1)
        c = Canvas(S, S)
        heat_age = max(0.0, 1.0 - p * 1.15)
        rise = min(1.0, max(0.0, (p - 0.12) / 0.55))
        cap_cy = 118 - (14 + 64 * rise)
        cap_rx = 14 + 40 * min(1.0, p / 0.65)
        cap_ry = cap_rx * 0.52
        stem_w = 4 + 9 * min(1.0, max(0.0, (p - 0.1) / 0.4))
        skirt_rx = 10 + 52 * min(1.0, p / 0.6)
        skirt_ry = 5 + 7 * min(1.0, p / 0.6)
        for y in range(S):
            for x in range(S):
                best = -1.0
                n = _fbm(x / 9.0, (y + f * 3) / 9.0, 5)
                # fireball / cap
                dx, dy = (x - 64) / cap_rx, (y - cap_cy) / cap_ry
                d = math.hypot(dx, dy) * (0.85 + 0.3 * n)
                if d < 1.0:
                    core = (1 - d) * 1.2 + (0.25 if dy > 0.2 else 0)  # glowing underside
                    best = max(best, min(1.0, core * (0.35 + 0.65 * heat_age) + 0.1 * n))
                # stem
                if cap_cy < y <= 127 and p > 0.08:
                    w = stem_w * (0.75 + 0.5 * n) * (0.7 + 0.3 * (y - cap_cy) / max(1, 127 - cap_cy))
                    if abs(x - 64) < w:
                        k = 1 - abs(x - 64) / w
                        best = max(best, min(1.0, 0.25 + 0.5 * k * heat_age + 0.15 * n))
                # ground skirt
                dx2, dy2 = (x - 64) / skirt_rx, (y - (127 - skirt_ry * 0.5)) / skirt_ry
                d2 = math.hypot(dx2, dy2) * (0.8 + 0.4 * n)
                if d2 < 1.0 and y <= 127:
                    best = max(best, min(1.0, 0.15 + 0.35 * (1 - d2) * heat_age + 0.12 * n))
                if best >= 0:
                    c.p(x, y, _heat(best))
        # first frame: pure flash ball
        if f == 0:
            c.disc(64, 120, 9, hexc("FFF8E8"))
        frames.append(c)
    save_sheet("Assets/Art/Endings/nuke_explosion.png", frames, cols=7, pivot=(0.5, 0.0), group="Nuke",
               animations=[("Nuke_Blast", list(range(N)), 6, False)])
    MANIFEST["controllers"].append(_loop_ctrl("Nuke", "Assets/Art/Endings/nuke_explosion.png", "Nuke_Blast"))

    # ---- bunker ruins (160 x 56)
    rnd = random.Random(808)
    r = Canvas(160, 56)
    for x in range(160):
        h = int(22 * math.sin(math.pi * x / 159) ** 0.7 * (0.8 + 0.4 * _vnoise(x / 7.0, 0, 9)))
        r.vline(x, 55 - h, 55, hexc("1A1412"))
        r.p(x, 55 - h, hexc("2A201C"))
    for _ in range(26):  # concrete chunks
        cx, cy = rnd.randint(30, 130), rnd.randint(34, 52)
        w, hh = rnd.randint(3, 9), rnd.randint(2, 6)
        r.rect(cx, cy, w, hh, hexc("3A3A38"))
        r.hline(cx, cx + w - 1, cy, hexc("555550"))
    for _ in range(8):  # rebar
        x0 = rnd.randint(40, 120)
        r.line(x0, 40, x0 + rnd.randint(-6, 6), 40 - rnd.randint(5, 12), P["rust1"])
    for _ in range(30):  # embers
        r.p(rnd.randint(30, 130), rnd.randint(36, 54), rnd.choice([P["a2"], P["r2"], P["a3"]]))
    for k in range(5):  # smoke wisps
        sx = 50 + k * 15
        for t in range(18):
            r.p(sx + int(3 * math.sin(t / 3 + k)), 36 - t, with_alpha(P["m3"], max(20, 140 - t * 7)))
    save_sheet("Assets/Art/Endings/bunker_ruins.png", [r], pivot=(0.5, 0.0), group="Endings")

    # ---- dawn sky (good ending)
    W, H = 320, 180
    sky = Canvas(W, H)
    stops = [(0, hexc("1A2A44")), (60, hexc("4A5A7A")), (100, hexc("A07A78")), (120, hexc("E0A070")), (132, hexc("F4C27A")), (142, hexc("3A2A2C")), (180, hexc("1A1418"))]
    for y in range(H):
        for (y0, c0), (y1, c1) in zip(stops, stops[1:]):
            if y0 <= y <= y1:
                t = (y - y0) / max(1, y1 - y0)
                sky.hline(0, W - 1, y, tuple(int(c0[i] * (1 - t) + c1[i] * t) for i in range(3)) + (255,))
                break
    rnd = random.Random(909)
    for _ in range(25):
        sky.p(rnd.randrange(W), rnd.randrange(0, 40), hexc("8A94B8"))
    _glow(sky, 236, 130, 70, hexc("FFE29A"), 0.35)
    sky.disc(236, 132, 15, hexc("FFE8A8"))
    x = 0
    while x < W:  # skyline with lit windows: the city is waking up
        w = rnd.randint(6, 18)
        h = rnd.randint(8, 34)
        top = 132 - h
        sky.rect(x, top, w, 132 - top, hexc("2A1E26"))
        for _ in range(rnd.randint(1, 5)):
            sky.p(x + rnd.randrange(w), top + rnd.randrange(max(1, h - 2)), rnd.choice([P["a2"], P["a3"], P["g3"]]))
        x += w + rnd.randint(1, 8)
    for px in (40, 140, 240, 340):
        sky.line(px - 5, 136, px, 96, hexc("2A1E26"))
        sky.line(px + 5, 136, px, 96, hexc("2A1E26"))
        sky.hline(px - 8, px + 8, 102, hexc("2A1E26"))
        sky.p(px, 95, P["g3"])  # pylons have power again
    for xx in range(W):
        h1 = 140 + 5 * math.sin(xx / 37) + 3 * math.sin(xx / 13 + 1)
        sky.vline(xx, int(h1), H - 1, hexc("241A1E"))
    save_sheet("Assets/Art/Endings/bg_exterior_dawn.png", [sky], pivot=(0.5, 0.5), group="Endings")

    # ---- solid white (tint / darkness overlays, coloured in the scene)
    save_sheet("Assets/Art/Endings/solid_white.png", [Canvas(4, 4, (255, 255, 255, 255))], pivot=(0.5, 0.5), group="Endings")


# ==========================================================================
# DECORATION
# ==========================================================================
def gen_decor():
    # Vent fan (16x16, 4 frames)
    frames = []
    for f in range(4):
        c = Canvas(16, 16)
        c.bevel(0, 0, 16, 16, P["m1"], P["m2"], P["m0"])
        c.disc(8, 8, 6.5, P["ink"])
        ang = f * 22.5
        for b in range(4):
            a = math.radians(ang + b * 90)
            for t in range(1, 6):
                x = 8 + math.cos(a) * t - 0.5
                y = 8 + math.sin(a) * t - 0.5
                c.p(round(x), round(y), P["m3"])
                c.p(round(x + math.cos(a + 1.57)), round(y + math.sin(a + 1.57)), P["m2"])
        c.rect(7, 7, 2, 2, P["m4"])
        for x, y in ((1, 1), (14, 1), (1, 14), (14, 14)):
            c.p(x, y, P["m3"])
        frames.append(c)
    save_sheet("Assets/Art/Decor/vent_fan.png", frames, pivot=(0.5, 0.5), group="VentFan",
               animations=[("VentFan_Spin", [0, 1, 2, 3], 16, True)])
    MANIFEST["controllers"].append(_loop_ctrl("VentFan", "Assets/Art/Decor/vent_fan.png", "VentFan_Spin"))

    # Warning beacon (16x16, 4 frames)
    frames = []
    for f in range(4):
        c = Canvas(16, 16)
        c.rect(4, 12, 8, 3, P["m2"])
        c.hline(4, 11, 12, P["m4"])
        c.rect(5, 5, 6, 7, P["a1"])
        c.hline(6, 9, 4, P["a1"])
        band = [5, 7, 9, 7][f]
        c.vline(band, 5, 11, P["a3"])
        c.vline(band + 1, 5, 11, P["a2"])
        c.outline()
        if f in (0, 1):
            c.p(1 if f == 0 else 14, 7, with_alpha(P["a2"], 160))
            c.p(0 if f == 0 else 15, 7, with_alpha(P["a2"], 90))
        frames.append(c)
    save_sheet("Assets/Art/Decor/warning_beacon.png", frames, pivot=(0.5, 0.0), group="WarningBeacon",
               animations=[("WarningBeacon_Spin", [0, 1, 2, 3], 8, True)])
    MANIFEST["controllers"].append(_loop_ctrl("WarningBeacon", "Assets/Art/Decor/warning_beacon.png", "WarningBeacon_Spin"))

    # Mainframe tape drive (16x32, 6 frames)
    frames = []
    for f in range(6):
        rnd = random.Random(f * 13)
        c = Canvas(16, 32)
        c.bevel(1, 0, 14, 32, P["m2"], P["m3"], P["m1"])
        c.rect(3, 2, 10, 20, P["m1"])
        draw_reel(c, 8, 7, 4.3, f * 20, 3.6)
        draw_reel(c, 8, 17, 4.3, f * 20 + 40, 2.4)
        for y in range(24, 30, 2):
            for x in range(3, 13, 2):
                r = rnd.random()
                c.p(x, y, P["g2"] if r < 0.4 else (P["a2"] if r < 0.5 else P["m0"]))
        c.outline()
        frames.append(c)
    save_sheet("Assets/Art/Decor/mainframe_tape_drive.png", frames, pivot=(0.5, 0.0), group="Mainframe",
               animations=[("Mainframe_Run", [0, 1, 2, 3, 4, 5], 6, True)])
    MANIFEST["controllers"].append(_loop_ctrl("Mainframe", "Assets/Art/Decor/mainframe_tape_drive.png", "Mainframe_Run"))

    # Ceiling lamp (16x16, 3 frames) - flicker sequence
    frames = []
    for lvl in range(3):  # 0 on, 1 dim, 2 off
        c = Canvas(16, 16)
        c.vline(8, 0, 3, P["ink"])
        c.rect(4, 4, 8, 3, P["m2"])
        c.hline(4, 11, 4, P["m4"])
        bulb = [P["a3"], P["a2"], P["a0"]][lvl]
        c.rect(6, 7, 4, 2, bulb)
        c.outline()
        if lvl < 2:
            for i, y in enumerate(range(9, 14)):
                a = (110 - i * 22) // (lvl + 1)
                c.hline(6 - i, 9 + i, y, with_alpha(P["a2"], max(a, 0)))
        frames.append(c)
    seq = [0] * 10 + [1, 0, 2, 0] + [0] * 6 + [2, 1]
    save_sheet("Assets/Art/Decor/ceiling_lamp.png", frames, pivot=(0.5, 1.0), group="CeilingLamp",
               animations=[("CeilingLamp_Flicker", seq, 12, True)])
    MANIFEST["controllers"].append(_loop_ctrl("CeilingLamp", "Assets/Art/Decor/ceiling_lamp.png", "CeilingLamp_Flicker"))

    # Static props (16x16)
    props = []
    # 0 cable hang A
    c = Canvas(16, 16)
    for t in range(32):
        x = t / 2
        c.p(int(x), int(2 + 8 * math.sin(math.pi * t / 32)), P["ink"])
        c.p(int(x), int(4 + 5 * math.sin(math.pi * t / 32)), P["r1"])
    props.append(c)
    # 1 cable dangling
    c = Canvas(16, 16)
    c.vline(5, 0, 11, P["ink"])
    c.vline(10, 0, 8, P["g1"])
    c.rect(4, 12, 3, 2, P["m3"])
    c.p(5, 14, P["a2"])
    c.rect(9, 9, 3, 2, P["m3"])
    props.append(c)
    # 2 high voltage sign
    c = Canvas(16, 16)
    for y in range(12):
        c.hline(8 - y // 2 - 1, 7 + y // 2 + 1, 2 + y, P["a2"])
    c.outline()
    c.ascii(6, 5, ["..#", ".#.", "###", ".#.", "#.."], {"#": P["ink"]})
    props.append(c)
    # 3 REC sign
    c = Canvas(16, 16)
    c.rect(0, 4, 16, 8, P["r1"])
    c.box(0, 4, 16, 8, P["ink"])
    c.rect(1, 7, 2, 2, P["r3"])
    c.ascii(4, 6, ["##.", "#.#", "##.", "#.#"], {"#": P["white"]})
    c.ascii(8, 6, ["###", "##.", "#..", "###"], {"#": P["white"]})
    c.ascii(12, 6, ["###", "#..", "#..", "###"], {"#": P["white"]})
    props.append(c)
    # 4 arrow sign
    c = Canvas(16, 16)
    c.rect(1, 4, 14, 8, P["g1"])
    c.box(1, 4, 14, 8, P["ink"])
    draw_glyph(c, 6, 4, "RIGHT", P["g3"])
    props.append(c)
    # 5 loose tape reel
    c = Canvas(16, 16)
    draw_reel(c, 8, 9, 6.5, 15, 5.0)
    c.outline()
    props.append(c)
    # 6 crate
    c = Canvas(16, 16)
    c.bevel(1, 3, 14, 13, P["rust1"], P["rust2"], P["rust0"])
    c.line(2, 4, 13, 14, P["rust0"])
    c.line(13, 4, 2, 14, P["rust0"])
    c.box(1, 3, 14, 13, P["ink"])
    props.append(c)
    # 7 broken small monitor
    c = Canvas(16, 16)
    c.bevel(1, 3, 14, 12, P["m2"], P["m3"], P["m1"])
    c.rect(3, 5, 10, 7, P["m0"])
    c.line(4, 6, 8, 10, P["m3"])
    c.line(8, 10, 11, 7, P["m3"])
    c.p(7, 8, P["g1"])
    c.outline()
    props.append(c)
    # 8 paper note (ties into existing note art)
    c = Canvas(16, 16)
    c.rect(3, 2, 10, 13, P["paper"])
    c.p(12, 2, CLEAR)
    c.p(11, 2, P["paper2"])
    c.p(12, 3, P["paper2"])
    for y in range(5, 13, 2):
        c.hline(5, 5 + (y * 3) % 6 + 2, y, P["rust1"])
    c.p(10, 12, P["r1"])
    c.outline()
    props.append(c)
    # 9 valve wheel
    c = Canvas(16, 16)
    c.disc(8, 8, 6, P["r1"])
    c.disc(8, 8, 4.5, CLEAR)
    c.line(3, 8, 12, 8, P["r1"])
    c.line(8, 3, 8, 12, P["r1"])
    c.rect(7, 7, 2, 2, P["m4"])
    c.p(5, 3, P["r2"])
    c.outline()
    props.append(c)
    save_sheet("Assets/Art/Decor/props_16.png", props, cols=5, pivot=(0.5, 0.0), group="Props")


def _loop_ctrl(name, sheet_path, clip):
    return {"name": name, "sheet": sheet_path, "folder": name, "defaultState": "Loop", "sortingOrder": 0,
            "parameters": [], "states": [{"name": "Loop", "clip": clip}], "transitions": []}


# ==========================================================================
# EFFECTS
# ==========================================================================
def gen_effects():
    # Sparks (16x16, 6 frames)
    rnd = random.Random(5)
    parts = [(rnd.uniform(-2.5, 2.5), rnd.uniform(-3.5, -0.5)) for _ in range(9)]
    frames = []
    for f in range(6):
        c = Canvas(16, 16)
        if f == 0:
            c.disc(8, 8, 2.2, P["a3"])
            c.p(8, 8, P["white"])
        for vx, vy in parts:
            t = f * 0.9 + 0.6
            x = 8 + vx * t
            y = 8 + vy * t + 0.45 * t * t
            col = [P["white"], P["a3"], P["a2"], P["a2"], P["a1"], P["a0"]][f]
            c.p(x, y, col)
            if f < 3:
                c.p(x - vx * 0.4, y - vy * 0.4, P["a2"])
        frames.append(c)
    save_sheet("Assets/Art/Effects/sparks.png", frames, pivot=(0.5, 0.5), group="Sparks",
               animations=[("Sparks_Burst", [0, 1, 2, 3, 4, 5], 18, False)])
    MANIFEST["controllers"].append(_loop_ctrl("Sparks", "Assets/Art/Effects/sparks.png", "Sparks_Burst"))

    # Dust puff (16x8, 5 frames) - jump / land
    frames = []
    for f in range(5):
        c = Canvas(16, 8)
        spread = 2 + f * 1.4
        col = with_alpha(P["m4"], 230 - f * 45)
        for side in (-1, 1):
            cx = 8 + side * spread
            c.disc(cx, 6 - f * 0.4, max(2.2 - f * 0.35, 0.6), col)
        frames.append(c)
    save_sheet("Assets/Art/Effects/dust_puff.png", frames, pivot=(0.5, 0.0), group="DustPuff",
               animations=[("DustPuff_Play", [0, 1, 2, 3, 4], 16, False)])
    MANIFEST["controllers"].append(_loop_ctrl("DustPuff", "Assets/Art/Effects/dust_puff.png", "DustPuff_Play"))

    # Recordable-object marker brackets (16x16): 0-3 red (REC), 4-7 green (PLAY), 8 gray (registered)
    frames = []
    for col, n in ((P["r2"], 4), (P["g3"], 4), (P["m4"], 1)):
        for f in range(n):
            c = Canvas(16, 16)
            inset = [0, 1, 1, 0][f] if n > 1 else 0
            a, b = inset, 15 - inset
            for (x, y, dx, dy) in ((a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)):
                for k in range(4):
                    c.p(x + dx * k, y, col)
                    c.p(x, y + dy * k, col)
            frames.append(c)
    save_sheet("Assets/Art/Effects/record_marker.png", frames, cols=9, pivot=(0.5, 0.5), group="RecordMarker",
               border=(5, 5, 5, 5),
               animations=[("RecordMarker_Rec", [0, 1, 2, 3], 6, True),
                           ("RecordMarker_Play", [4, 5, 6, 7], 6, True),
                           ("RecordMarker_Registered", [8], 1, True)])
    mode_controller("RecordMarker", MANIFEST["sheets"][-1], [
        ("Registered", "RecordMarker_Registered"), ("Rec", "RecordMarker_Rec"), ("Play", "RecordMarker_Play")],
        sorting=20)

    # Interaction prompt: [E] keycap bobbing (16x16, 4 frames)
    frames = []
    for f in range(4):
        c = Canvas(16, 16)
        dy = [0, 0, 1, 1][f]
        draw_keycap(c, 1, 1 + dy, 14, 12, "E", pressed=False)
        c.p(7, 14 + dy, P["ink"])
        c.p(8, 14 + dy, P["ink"])
        frames.append(c)
    save_sheet("Assets/Art/Effects/interact_prompt.png", frames, pivot=(0.5, 0.0), group="InteractPrompt",
               animations=[("InteractPrompt_Bob", [0, 1, 2, 3], 4, True)])
    MANIFEST["controllers"].append(_loop_ctrl("InteractPrompt", "Assets/Art/Effects/interact_prompt.png", "InteractPrompt_Bob"))

    # Full-screen rewind glitch overlay (320x180, 4 frames)
    W, H = 320, 180
    frames = []
    for f in range(4):
        rnd = random.Random(77 + f)
        c = Canvas(W, H)
        band_y = (f * 47) % H
        for y in range(band_y, min(H, band_y + 14)):
            for x in range(W):
                if rnd.random() < 0.35:
                    c.p(x, y, with_alpha(P["white"], rnd.randint(40, 120)))
        for _ in range(26):
            y = rnd.randrange(H)
            x0 = rnd.randrange(W)
            ln = rnd.randint(20, 140)
            col = rnd.choice([P["a2"], P["a3"], P["white"], P["g3"]])
            c.hline(x0, min(W - 1, x0 + ln), y, with_alpha(col, rnd.randint(60, 150)))
        # left/right "<<" chevrons hint
        for k in range(2):
            draw_text(c, 12 + k * 8, 12, "<", with_alpha(P["a2"], 200), scale=1)
        frames.append(c)
    save_sheet("Assets/Art/Effects/rewind_glitch_overlay.png", frames, cols=2, pivot=(0.5, 0.5),
               group="RewindGlitch",
               animations=[("RewindGlitch_Play", [0, 1, 2, 3, 1, 0], 20, True)])
    MANIFEST["controllers"].append(_loop_ctrl("RewindGlitch", "Assets/Art/Effects/rewind_glitch_overlay.png", "RewindGlitch_Play"))

    # CRT scanline + vignette overlay (320x180, 1 frame)
    c = Canvas(W, H)
    for y in range(H):
        for x in range(W):
            dx, dy = (x - W / 2) / (W / 2), (y - H / 2) / (H / 2)
            v = max(0.0, (dx * dx + dy * dy) - 0.55) * 0.9
            a = int(min(1.0, v) * 170)
            if y % 2 == 1:
                a = max(a, 38)
            if a:
                c.p(x, y, (0, 0, 0, a))
    save_sheet("Assets/Art/Effects/crt_overlay.png", [c], pivot=(0.5, 0.5), group="CRTOverlay")


# ==========================================================================
# UI
# ==========================================================================
def draw_keycap(c, x, y, w, h, label, pressed=False):
    face = P["m2"] if not pressed else P["m1"]
    off = 1 if pressed else 0
    c.rect(x, y + 1, w, h - 1, P["ink"])
    c.rect(x + 1, y + off, w - 2, h - 2, face)
    c.hline(x + 1, x + w - 2, y + off, P["m4"] if not pressed else P["m2"])
    c.rect(x + 1, y + h - 2, w - 2, 1, P["m0"])
    c.vline(x, y + 1, y + h - 2, P["ink"])
    c.vline(x + w - 1, y + 1, y + h - 2, P["ink"])
    c.hline(x + 1, x + w - 2, y - 1 + off, P["ink"])
    col = P["g3"]
    if label in FONT:
        draw_glyph(c, x + (w - 5) // 2, y + off + (h - 9) // 2 + 1, label, col)
    else:
        tw = text_width(label)
        draw_text(c, x + (w - tw) // 2, y + off + (h - 9) // 2 + 1, label, col)


def gen_ui():
    # Keycaps 16x16: normal row + pressed row
    keys = ["A", "D", "E", "R", "F", "Q", "LEFT", "RIGHT"]
    frames = []
    for pressed in (False, True):
        for k in keys:
            c = Canvas(16, 16)
            draw_keycap(c, 1, 2, 14, 13, k, pressed)
            frames.append(c)
    anims = [(f"Key_{k}_Press", [i, i + len(keys)], 2, True) for i, k in enumerate(keys)]
    save_sheet("Assets/Art/UI/keys_16.png", frames, cols=8, pivot=(0.5, 0.5), group="UIKeys", animations=anims)

    frames = []
    for pressed in (False, True):
        c = Canvas(24, 16)
        draw_keycap(c, 1, 2, 22, 13, "ESC", pressed)
        frames.append(c)
    save_sheet("Assets/Art/UI/key_esc.png", frames, pivot=(0.5, 0.5), group="UIKeys",
               animations=[("Key_Esc_Press", [0, 1], 2, True)])
    frames = []
    for pressed in (False, True):
        c = Canvas(40, 16)
        draw_keycap(c, 1, 2, 38, 13, "SPACE", pressed)
        frames.append(c)
    save_sheet("Assets/Art/UI/key_space.png", frames, pivot=(0.5, 0.5), group="UIKeys",
               animations=[("Key_Space_Press", [0, 1], 2, True)])

    # Tape mode icons (16x16): IDLE, REC, PLAY, REW, FULL, STOP  x  bright / dim
    def icon(kind, bright):
        c = Canvas(16, 16)
        f = 1.0 if bright else 0.45
        def k(col):
            return tuple(int(v * f) for v in col[:3]) + (255,)
        if kind == "IDLE":
            c.rect(4, 4, 8, 8, k(P["m4"]))
        elif kind == "REC":
            c.disc(8, 8, 5, k(P["r2"]))
            c.p(6, 5, k(P["r3"]))
        elif kind == "PLAY":
            for i in range(10):
                c.vline(4 + i, 3 + i // 2, 12 - i // 2, k(P["g3"]))
        elif kind == "REW":
            for off in (0, 6):
                for i in range(6):
                    c.vline(8 + off - i - 3 + 3, 8 - (5 - i) - 1 + 1, 8 + (5 - i) - 1, k(P["a2"]))
        elif kind == "FULL":
            for y in range(11):
                c.hline(8 - y // 2 - 1, 7 + y // 2 + 1, 3 + y, k(P["r2"]))
            c.vline(8, 6, 10, P["ink"])
            c.vline(7, 6, 10, P["ink"])
            c.rect(7, 12, 2, 1, P["ink"])
        elif kind == "STOP":
            c.rect(4, 4, 8, 8, k(P["white"]))
        c.outline()
        return c

    kinds = ["IDLE", "REC", "PLAY", "REW", "FULL", "STOP"]
    frames = [icon(k, True) for k in kinds] + [icon(k, False) for k in kinds]
    anims = [(f"Icon_{k.title()}_Blink", [i, i + 6], 3, True) for i, k in enumerate(kinds)]
    save_sheet("Assets/Art/UI/tape_mode_icons.png", frames, cols=6, pivot=(0.5, 0.5), group="UIIcons",
               animations=anims)

    # HUD cassette (32x16, 6 frames reel spin)
    frames = []
    for f in range(6):
        c = Canvas(32, 16)
        c.bevel(1, 1, 30, 14, P["m2"], P["m3"], P["m1"])
        c.rect(4, 3, 24, 5, P["paper"])
        c.hline(5, 18, 4, P["r1"])
        c.rect(7, 8, 18, 5, P["ink"])
        draw_reel(c, 11, 10.5, 2.6, f * 20, 2.6)
        draw_reel(c, 21, 10.5, 2.6, f * 20 + 30, 1.8)
        c.rect(14, 9, 4, 3, P["tape"])
        c.outline()
        frames.append(c)
    save_sheet("Assets/Art/UI/hud_cassette.png", frames, pivot=(0.5, 0.5), group="UICassette",
               animations=[("HudCassette_Spin", [0, 1, 2, 3, 4, 5], 12, True),
                           ("HudCassette_Rewind", [5, 3, 1], 18, True),
                           ("HudCassette_Idle", [0], 1, True)])

    # 9-slice panels (24x24, border 6): green / amber / red
    frames = []
    for col, dim in ((P["g3"], P["g1"]), (P["a2"], P["a1"]), (P["r2"], P["r1"])):
        c = Canvas(24, 24, with_alpha(P["bg"], 235))
        c.box(0, 0, 24, 24, P["ink"])
        c.box(1, 1, 22, 22, dim)
        c.box(2, 2, 20, 20, P["ink"])
        for (x, y) in ((1, 1), (22, 1), (1, 22), (22, 22)):
            c.p(x, y, col)
        c.hline(3, 6, 1, col)
        c.hline(17, 20, 22, col)
        for y in range(3, 21, 2):
            c.hline(3, 20, y, with_alpha(P["bg2"], 235))
        frames.append(c)
    save_sheet("Assets/Art/UI/panel_9slice.png", frames, pivot=(0.5, 0.5), border=(6, 6, 6, 6), group="UIPanels")

    # 9-slice buttons (32x16, border 5): normal / hover / pressed
    frames = []
    for state in range(3):
        c = Canvas(32, 16)
        fill = [P["bg"], P["g0"], P["g1"]][state]
        edge = [P["g1"], P["g3"], P["g4"]][state]
        c.rect(1, 1, 30, 14, fill)
        c.box(0, 0, 32, 16, P["ink"])
        for (x0, d) in ((1, 1), (30, -1)):
            c.vline(x0, 2, 13, edge)
            c.p(x0 + d, 1, edge)
            c.p(x0 + d, 14, edge)
        frames.append(c)
    save_sheet("Assets/Art/UI/button_9slice.png", frames, pivot=(0.5, 0.5), border=(5, 5, 5, 5), group="UIButtons")

    # Memory bar frame (9-slice) + cells
    c = Canvas(16, 12)
    c.rect(0, 0, 16, 12, P["ink"])
    c.box(1, 1, 14, 10, P["g1"])
    c.rect(2, 2, 12, 8, P["bg"])
    save_sheet("Assets/Art/UI/memory_bar_frame.png", [c], pivot=(0.5, 0.5), border=(3, 3, 3, 3), group="UIMemoryBar")
    cells = []
    for col in (None, P["g3"], P["a2"], P["r2"]):
        c = Canvas(4, 8)
        if col is None:
            c.rect(0, 0, 3, 8, P["m0"])
        else:
            c.rect(0, 0, 3, 8, col)
            c.hline(0, 2, 0, P["white"] if col != P["r2"] else P["r3"])
            c.hline(0, 2, 7, tuple(int(v * 0.6) for v in col[:3]) + (255,))
        cells.append(c)
    save_sheet("Assets/Art/UI/memory_bar_cells.png", cells, pivot=(0.0, 0.5), group="UIMemoryBar")

    # Blinking cursor ">" (8x8)
    frames = []
    for on in (True, False):
        c = Canvas(8, 8)
        if on:
            draw_glyph(c, 1, 0, ">", P["g3"])
        frames.append(c)
    save_sheet("Assets/Art/UI/cursor.png", frames, pivot=(0.5, 0.5), group="UICursor",
               animations=[("Cursor_Blink", [0, 1], 2, True)])

    # Tileable CRT scanlines for UI screens (1x4 texels, wrap = Repeat so a Tiled Image is one quad)
    c = Canvas(1, 4)
    c.p(0, 2, (0, 0, 0, 70))
    c.p(0, 3, (0, 0, 0, 110))
    save_sheet("Assets/Art/UI/ui_scanlines.png", [c], pivot=(0.5, 0.5), group="UIScanlines", wrap_repeat=True)

    # Title logo (2 frames: clean + glitch)
    def logo(glitch):
        c = Canvas(176, 48)
        draw_text(c, 4, 4 + 3, "REWIND", P["g1"], scale=3, spacing=1)
        draw_text(c, 4, 4, "REWIND", P["g3"], scale=3, spacing=1)
        x2 = 4 + text_width("REWIND", 3, 1) + 4
        draw_text(c, x2, 4 + 7, ".exe", P["a2"], scale=2)
        sub = "AN ANALOG EXPERIMENT"
        draw_text(c, (176 - text_width(sub)) // 2, 36, sub, P["white"])
        # scan gaps
        for y in range(0, 30, 3):
            for x in range(176):
                p = c.px[x, y]
                if p[3]:
                    c.px[x, y] = (int(p[0] * 0.7), int(p[1] * 0.7), int(p[2] * 0.7), 255)
        if glitch:
            src = c.im.copy().load()
            for y in (8, 9, 17, 18, 19, 26):
                for x in range(176):
                    c.px[x, y] = src[(x - 4) % 176, y]
        return c

    save_sheet("Assets/Art/UI/title_logo.png", [logo(False), logo(True)], pivot=(0.5, 0.5), group="UILogo",
               animations=[("TitleLogo_Flicker", [0] * 14 + [1, 0, 1], 12, True)])
    MANIFEST["controllers"].append(_loop_ctrl("TitleLogo", "Assets/Art/UI/title_logo.png", "TitleLogo_Flicker"))


# ==========================================================================
def write_preview():
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    for rel, im in PREVIEWS:
        scale = 4 if max(im.size) <= 400 else 2
        bg = Image.new("RGBA", im.size, (40, 40, 48, 255))
        # checker for transparency
        px = bg.load()
        for y in range(im.size[1]):
            for x in range(im.size[0]):
                if ((x // 4) + (y // 4)) % 2:
                    px[x, y] = (52, 52, 62, 255)
        bg.alpha_composite(im)
        bg = bg.resize((im.size[0] * scale, im.size[1] * scale), Image.NEAREST)
        bg.save(os.path.join(PREVIEW_DIR, os.path.basename(rel)))


def main():
    print("Generating REWIND.exe art...")
    gen_operator()
    gen_tileset()
    gen_backgrounds()
    gen_bg_archive()
    gen_bg_generator()
    gen_bg_core()
    gen_tape_recorder()
    gen_door()
    gen_switch()
    gen_platform()
    gen_conveyor()
    gen_crt_monitor()
    gen_main_terminal()
    gen_main_computer()
    gen_small_terminal()
    gen_decor()
    gen_effects()
    gen_ui()
    gen_intro_art()
    gen_ending_art()
    MANIFEST["pixelsPerUnit"] = 16
    out = os.path.join(ART, "art_manifest.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(MANIFEST, fh, indent=2)
    print(f"Manifest: {len(MANIFEST['sheets'])} sheets, {len(MANIFEST['controllers'])} controllers")
    if "--preview" in sys.argv:
        global PREVIEW_DIR
        i = sys.argv.index("--preview")
        if i + 1 < len(sys.argv):
            PREVIEW_DIR = sys.argv[i + 1]
        write_preview()
        print("Previews ->", PREVIEW_DIR)


if __name__ == "__main__":
    main()
