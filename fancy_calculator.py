"""
Fancy Scientific Calculator - one self-contained file, nothing to install.

Everything is drawn by hand on a tkinter Canvas: a gradient background with
glowing orbs, rounded 3D buttons that light up on hover and squish when
pressed, a glowing display with a blinking caret, confetti when you press =,
a shake when something goes wrong, and four colour themes.

Run it:   python fancy_calculator.py

Mouse:    click the buttons. Click the result to copy it.
Keyboard: type straight in. Enter or = evaluates, Backspace deletes,
          Esc clears, Ctrl+V pastes, Ctrl+C copies the result.
Top bar:  the DEG/RAD pill switches the angle mode; the theme pill cycles
          through Neon, Candy, Ocean and Sunset.

After a result, typing a number starts fresh, while typing an operator
carries on from the answer (so "=" then "+ 5" means "ans + 5").

The file has two halves: the calculator ENGINE (tokenizer + parser), then
the GUI that sits on top of it.
"""

import math
import random
import re
import sys
import tkinter as tk
from tkinter import font as tkfont

# ===========================================================================
#  ENGINE: tokenizer + recursive descent parser (same as scientific_calculator.py)
# ===========================================================================

# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

TOKEN_PATTERN = re.compile(
    r"\s*("
    r"\d+\.?\d*(?:[eE][-+]?\d+)?"    # 12, 3.5, 1e3, 2.5e-4
    r"|\.\d+(?:[eE][-+]?\d+)?"       # .5, .5e2
    r"|\*\*"                         # ** (same as ^)
    r"|[A-Za-z_]\w*"                 # names: pi, sin, ans ...
    r"|[-+*/^%!(),]"                 # single-character symbols
    r")"
)
NUMBER_PATTERN = re.compile(r"\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?")
NAME_PATTERN = re.compile(r"[a-z_]\w*")


def tokenize(text):
    text = text.strip().lower()
    tokens = []
    pos = 0
    while pos < len(text):
        match = TOKEN_PATTERN.match(text, pos)
        if not match:
            raise ValueError(f"Unexpected character: {text[pos]!r}")
        token = match.group(1)
        tokens.append("^" if token == "**" else token)
        pos = match.end()
    return tokens


# ---------------------------------------------------------------------------
# Maths helpers (each one checks its own inputs and gives a clear error)
# ---------------------------------------------------------------------------

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b


def modulo(a, b):
    if b == 0:
        raise ValueError("Cannot take a remainder of zero")
    return a % b


def power(base, exponent):
    try:
        return math.pow(base, exponent)
    except ValueError:
        raise ValueError(
            "Invalid power (zero to a negative power, or a negative base "
            "with a fractional exponent)"
        ) from None


def factorial(x):
    if x < 0 or x != int(x):
        raise ValueError("Factorial needs a non-negative whole number")
    if x > 170:
        raise ValueError("Factorial too large (the maximum is 170!)")
    return float(math.factorial(int(x)))


def cube_root(x):
    return math.copysign(abs(x) ** (1 / 3), x)


# ---------------------------------------------------------------------------
# The calculator: parser + evaluator in one class so it can hold state
# (angle mode and the previous answer)
#
#   expression : term   (('+' | '-') term)*
#   term       : unary  (('*' | '/' | '%') unary)*
#   unary      : ('-' | '+') unary | power
#   power      : postfix ('^' unary)?
#   postfix    : primary '!'*
#   primary    : NUMBER | NAME | NAME '(' args ')' | '(' expression ')'
# ---------------------------------------------------------------------------

class Calculator:
    def __init__(self, mode="deg"):
        self.mode = mode          # "deg" or "rad"
        self.ans = 0.0            # previous result
        self.tokens = []
        self.pos = 0

        self.constants = {"pi": math.pi, "e": math.e, "tau": math.tau}

        # name -> (function, min arguments, max arguments)
        self.functions = {
            "sqrt": (math.sqrt, 1, 1),
            "cbrt": (getattr(math, "cbrt", cube_root), 1, 1),
            "abs": (abs, 1, 1),
            "exp": (math.exp, 1, 1),
            "ln": (math.log, 1, 1),
            "log": (lambda x, base=10: math.log(x, base), 1, 2),
            "log2": (math.log2, 1, 1),
            "floor": (lambda x: float(math.floor(x)), 1, 1),
            "ceil": (lambda x: float(math.ceil(x)), 1, 1),
            "sin": (lambda x: math.sin(self._to_radians(x)), 1, 1),
            "cos": (lambda x: math.cos(self._to_radians(x)), 1, 1),
            "tan": (self._tan, 1, 1),
            "asin": (lambda x: self._from_radians(math.asin(x)), 1, 1),
            "acos": (lambda x: self._from_radians(math.acos(x)), 1, 1),
            "atan": (lambda x: self._from_radians(math.atan(x)), 1, 1),
            "sinh": (math.sinh, 1, 1),
            "cosh": (math.cosh, 1, 1),
            "tanh": (math.tanh, 1, 1),
        }

    # -- angle helpers ------------------------------------------------------

    def _to_radians(self, x):
        return math.radians(x) if self.mode == "deg" else x

    def _from_radians(self, x):
        return math.degrees(x) if self.mode == "deg" else x

    def _tan(self, x):
        if self.mode == "deg" and x % 180 == 90:
            raise ValueError("tan() is undefined at this angle")
        return math.tan(self._to_radians(x))

    # -- public entry point -------------------------------------------------

    def evaluate(self, text):
        self.tokens = tokenize(text)
        self.pos = 0
        if not self.tokens:
            raise ValueError("Empty expression")
        try:
            result = self.parse_expression()
            if self.peek() is not None:
                raise ValueError(f"Unexpected token: {self.peek()!r}")
        except ZeroDivisionError:
            raise ValueError("Cannot divide by zero") from None
        except OverflowError:
            raise ValueError("Result too large") from None
        except RecursionError:
            raise ValueError("Expression too complex") from None

        if not math.isfinite(result):
            raise ValueError("Result too large")
        self.ans = result
        return result

    # -- token helpers ------------------------------------------------------

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def advance(self):
        token = self.peek()
        if token is None:
            raise ValueError("Unexpected end of expression")
        self.pos += 1
        return token

    def expect_closing_bracket(self):
        if self.peek() != ")":
            raise ValueError("Missing closing bracket")
        self.advance()

    # -- grammar rules, lowest precedence first -----------------------------

    def parse_expression(self):
        value = self.parse_term()
        while self.peek() in ("+", "-"):
            op = self.advance()
            right = self.parse_term()
            value = value + right if op == "+" else value - right
        return value

    def parse_term(self):
        value = self.parse_unary()
        while self.peek() in ("*", "/", "%"):
            op = self.advance()
            right = self.parse_unary()
            if op == "*":
                value = value * right
            elif op == "/":
                value = divide(value, right)
            else:
                value = modulo(value, right)
        return value

    def parse_unary(self):
        token = self.peek()
        if token == "-":
            self.advance()
            return -self.parse_unary()
        if token == "+":
            self.advance()
            return self.parse_unary()
        return self.parse_power()

    def parse_power(self):
        # The exponent goes through parse_unary, which gives us both
        # right-associativity (2^3^2 = 2^9) and negative exponents (2^-1).
        # Because unary minus sits above power, -2^2 correctly gives -4.
        base = self.parse_postfix()
        if self.peek() == "^":
            self.advance()
            return power(base, self.parse_unary())
        return base

    def parse_postfix(self):
        value = self.parse_primary()
        while self.peek() == "!":
            self.advance()
            value = factorial(value)
        return value

    def parse_primary(self):
        token = self.advance()

        if token == "(":
            value = self.parse_expression()
            self.expect_closing_bracket()
            return value

        if NUMBER_PATTERN.fullmatch(token):
            return float(token)

        if NAME_PATTERN.fullmatch(token):
            return self.parse_name(token)

        raise ValueError(f"Unexpected token: {token!r}")

    def parse_name(self, name):
        if name in self.functions:
            if self.peek() != "(":
                raise ValueError(f"{name}() needs brackets, e.g. {name}(30)")
            self.advance()
            args = []
            if self.peek() != ")":
                args.append(self.parse_expression())
                while self.peek() == ",":
                    self.advance()
                    args.append(self.parse_expression())
            self.expect_closing_bracket()
            return self.call(name, args)

        if name == "ans":
            return self.ans
        if name in self.constants:
            return self.constants[name]
        raise ValueError(f"Unknown name: {name!r}")

    def call(self, name, args):
        func, low, high = self.functions[name]
        if not low <= len(args) <= high:
            expected = str(low) if low == high else f"{low} or {high}"
            raise ValueError(f"{name}() takes {expected} argument(s)")
        try:
            return func(*args)
        except ValueError as error:
            if str(error) == "math domain error":
                raise ValueError(f"Invalid input for {name}()") from None
            raise


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_result(value):
    """Tidy floating-point noise: 0.30000000000000004 -> 0.3, 1.2e-16 -> 0."""
    if abs(value) < 1e-12:
        return "0"
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.12g}"



# ===========================================================================
#  GUI
# ===========================================================================

# ---------------------------------------------------------------------------
# Themes. "kinds" maps a button kind to (face colour, label colour).
# ---------------------------------------------------------------------------

THEMES = [
    {
        "name": "Neon",
        "bg": ("#1c0b3d", "#060d2b"),
        "panel": "#130a2e", "edge": "#9d6bff",
        "text": "#f6f1ff", "muted": "#9b90c9", "error": "#ff6b8b",
        "accent": "#18f2d2", "accent2": "#ff3df0",
        "hover": "#ffffff", "press": "#000000", "shadow": ("#000000", 0.55),
        "orbs": (("accent2", 0.30), ("accent", 0.20)),
        "kinds": {
            "num": ("#352a63", "#f6f1ff"),
            "fn": ("#251b4b", "#c4b5ff"),
            "op": ("#6d3df5", "#ffffff"),
            "clear": ("#e5305f", "#ffffff"),
            "eq": ("#ff3d9a", "#ffffff"),
            "pill": ("#130a2e", "#18f2d2"),
        },
    },
    {
        "name": "Candy",
        "bg": ("#ffe3f1", "#dde6ff"),
        "panel": "#ffffff", "edge": "#ff8cc6",
        "text": "#3b2553", "muted": "#a08bbd", "error": "#e0294a",
        "accent": "#ff4fa3", "accent2": "#7b8cff",
        "hover": "#ff8cc6", "press": "#7a5aa6", "shadow": ("#8a6bb3", 0.45),
        "orbs": (("accent2", 0.35), ("accent", 0.30)),
        "kinds": {
            "num": ("#ffffff", "#3b2553"),
            "fn": ("#f2e8ff", "#7a45c9"),
            "op": ("#ffc4e3", "#a3135f"),
            "clear": ("#ffb39a", "#8f1d0c"),
            "eq": ("#ff4fa3", "#ffffff"),
            "pill": ("#ffffff", "#ff4fa3"),
        },
    },
    {
        "name": "Ocean",
        "bg": ("#04202c", "#0a4358"),
        "panel": "#06242f", "edge": "#2ec4ff",
        "text": "#e9fbff", "muted": "#7fb7c8", "error": "#ff7a7a",
        "accent": "#2ec4ff", "accent2": "#ffd166",
        "hover": "#ffffff", "press": "#000000", "shadow": ("#000000", 0.50),
        "orbs": (("accent", 0.28), ("accent2", 0.18)),
        "kinds": {
            "num": ("#0f4b60", "#e9fbff"),
            "fn": ("#0a3544", "#8fe5ff"),
            "op": ("#1d7d99", "#ffffff"),
            "clear": ("#d7263d", "#ffffff"),
            "eq": ("#ffb703", "#2b1b00"),
            "pill": ("#06242f", "#2ec4ff"),
        },
    },
    {
        "name": "Sunset",
        "bg": ("#2b0a3d", "#7b2850"),
        "panel": "#1d0829", "edge": "#ff9d4d",
        "text": "#fff3e6", "muted": "#d4a5bd", "error": "#ff7b7b",
        "accent": "#ff9d4d", "accent2": "#ff4d8d",
        "hover": "#ffffff", "press": "#000000", "shadow": ("#14041c", 0.55),
        "orbs": (("accent2", 0.30), ("accent", 0.25)),
        "kinds": {
            "num": ("#4b1d58", "#fff3e6"),
            "fn": ("#36133f", "#ffb98a"),
            "op": ("#e8590c", "#ffffff"),
            "clear": ("#c2255c", "#ffffff"),
            "eq": ("#ffd43b", "#3b1700"),
            "pill": ("#1d0829", "#ff9d4d"),
        },
    },
]

# ---------------------------------------------------------------------------
# Button layout: (label, action, kind) or (label, action, kind, columns).
# An action starting with ":" is a command; anything else is typed in.
# ---------------------------------------------------------------------------

LAYOUT = [
    [("10^x", "10^", "fn"), ("ans", "ans", "fn"), ("(", "(", "fn"),
     (")", ")", "fn"), ("DEL", ":back", "op"), ("C", ":clear", "clear")],
    [("sin", "sin(", "fn"), ("cos", "cos(", "fn"), ("tan", "tan(", "fn"),
     ("ln", "ln(", "fn"), ("log", "log(", "fn"), ("n!", "!", "fn")],
    [("asin", "asin(", "fn"), ("acos", "acos(", "fn"), ("atan", "atan(", "fn"),
     ("exp", "exp(", "fn"), ("x^y", "^", "fn"), ("%", "%", "fn")],
    [("7", "7", "num"), ("8", "8", "num"), ("9", "9", "num"),
     ("÷", "/", "op"), ("π", "pi", "fn"), ("e", "e", "fn")],
    [("4", "4", "num"), ("5", "5", "num"), ("6", "6", "num"),
     ("×", "*", "op"), ("x²", "^2", "fn"), ("abs", "abs(", "fn")],
    [("1", "1", "num"), ("2", "2", "num"), ("3", "3", "num"),
     ("−", "-", "op"), ("√", "sqrt(", "fn"), ("cbrt", "cbrt(", "fn")],
    [("0", "0", "num"), (".", ".", "num"), (",", ",", "num"),
     ("+", "+", "op"), ("=", ":equals", "eq", 2)],
]

# Where the two glowing orbs sit: (x fraction, y fraction, radius as fraction of width)
ORB_SPOTS = ((0.12, 0.10, 0.55), (0.92, 0.62, 0.60))

# If the chosen font has no glyph for one of these symbols, plain ASCII is used instead.
FALLBACK_LABELS = {"π": "pi", "√": "sqrt", "×": "x", "÷": "/", "−": "-"}

OPERATOR_STARTS = "+-*/^%!"
PUNCTUATION = set(".,+-*/^%!() _")
MAX_EXPRESSION_LENGTH = 120


# ---------------------------------------------------------------------------
# Small drawing helpers
# ---------------------------------------------------------------------------

def _rgb(colour):
    colour = colour.lstrip("#")
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def lerp_colour(a, b, t):
    """Blend colour a towards colour b by t (0 = a, 1 = b)."""
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(
        round(x + (y - x) * t) for x, y in zip(_rgb(a), _rgb(b))
    )


def rounded_rect_points(x1, y1, x2, y2, r):
    """Points for a rounded rectangle; use with create_polygon(smooth=True)."""
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def star_points(cx, cy, r_out, r_in, points=4):
    coords = []
    for i in range(points * 2):
        angle = math.pi / 2 + i * math.pi / points
        r = r_out if i % 2 == 0 else r_in
        coords += [cx + r * math.cos(angle), cy - r * math.sin(angle)]
    return coords


def is_typable(char):
    return len(char) == 1 and char.isascii() and (char.isalnum() or char in PUNCTUATION)


def pick_font_family(root):
    available = {name.lower(): name for name in tkfont.families(root)}
    for wanted in ("Segoe UI", "SF Pro Display", "Helvetica Neue", "Inter",
                   "Poppins", "Arial", "DejaVu Sans", "Helvetica"):
        if wanted.lower() in available:
            return available[wanted.lower()]
    return "Helvetica"


class Control:
    """One clickable thing on the canvas: a calculator button or a top-bar pill."""

    def __init__(self, label, action, kind, row=0, col=0, span=1, pill=False):
        self.label = label
        self.action = action
        self.kind = kind
        self.row, self.col, self.span = row, col, span
        self.pill = pill
        self.rect = (0.0, 0.0, 0.0, 0.0)
        self.depth = 0.0        # height of the 3D "shadow" under the button
        self.radius = 0.0
        self.px = 14            # label size in pixels
        self.hover = 0.0        # animated 0..1
        self.pressed = False
        self.face = self.shadow = self.text = None

    def contains(self, x, y):
        x1, y1, x2, y2 = self.rect
        return x1 <= x <= x2 and y1 <= y <= y2


# ---------------------------------------------------------------------------
# The calculator window
# ---------------------------------------------------------------------------

class FancyCalculator:
    def __init__(self, root):
        self.root = root
        self.calc = Calculator()              # the engine above
        self.font_family = pick_font_family(root)
        self._fonts = {}

        # model: what the display shows
        self.expr = ""
        self.result_text = ""
        self.result_kind = "none"             # none | preview | final | error
        self.has_ans = False
        self.just_evaluated = False
        self.flash_msg = ""

        # animation / interaction state
        self.theme_index = 0
        self.hover_control = None
        self.active_control = None
        self.pop_frames = 0
        self.shake_frames = 0
        self.particles = []
        self.caret_on = True
        self.ready = False
        self.geom = {}
        self._tick_job = None
        self._redraw_job = None
        self.ans_item = self.expr_item = self.result_item = self.caret_item = None
        self._bg_image = None

        self.controls = []
        for row_index, row in enumerate(LAYOUT):
            col = 0
            for entry in row:
                label, action, kind = entry[:3]
                span = entry[3] if len(entry) > 3 else 1
                self.controls.append(Control(label, action, kind, row_index, col, span))
                col += span
        self.mode_pill = Control("DEG", ":mode", "pill", pill=True)
        self.theme_pill = Control("Neon", ":theme", "pill", pill=True)
        self.controls += [self.theme_pill, self.mode_pill]

        # Fonts without a glyph for a symbol would show it as "π"; avoid that.
        self.ellipsis = "…" if self.has_glyph("…") else "..."
        for ctrl in self.controls:
            ctrl.label = self.safe_label(ctrl.label)

        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0,
                                bg=self.theme["bg"][1])
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", self.on_leave)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        root.bind("<Key>", self.on_key)
        root.after(530, self._blink)

    @property
    def theme(self):
        return THEMES[self.theme_index]

    # -- fonts and text fitting ---------------------------------------------

    def font(self, px, weight="normal"):
        key = (int(px), weight)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(
                root=self.root, family=self.font_family, size=-int(px), weight=weight)
        return self._fonts[key]

    def has_glyph(self, char):
        """True if the font really draws this character. When a glyph is missing,
        Tk prints its code (like \\u03c0) instead, which is far wider than a letter."""
        font = self.font(20, "bold")
        return font.measure(char) <= 2.2 * font.measure("n")

    def safe_label(self, label):
        for char, fallback in FALLBACK_LABELS.items():
            if char in label and not self.has_glyph(char):
                label = label.replace(char, fallback)
        return label

    def fit_text(self, text, max_width, px, min_px, weight, keep):
        """Shrink the font until text fits; as a last resort, trim it with an ellipsis.
        keep="end" keeps the end of the text, keep="start" keeps the beginning."""
        px = int(px)
        while px > min_px and self.font(px, weight).measure(text) > max_width:
            px -= 2
        font = self.font(px, weight)
        shown = text
        if font.measure(text) > max_width:
            dots = self.ellipsis
            while len(shown) > 1:
                candidate = dots + shown if keep == "end" else shown + dots
                if font.measure(candidate) <= max_width:
                    break
                shown = shown[1:] if keep == "end" else shown[:-1]
            text = (dots + shown) if keep == "end" else (shown + dots)
        return text, px

    # -- layout ---------------------------------------------------------------

    def layout(self, width, height):
        m = max(12.0, width * 0.045)
        gap = max(6.0, width * 0.017)
        bar_h = max(30.0, height * 0.05)
        panel_h = max(120.0, min(210.0, height * 0.235))

        bar = (m, m, width - m, m + bar_h)
        panel_top = bar[3] + gap * 1.4
        panel = (m, panel_top, width - m, panel_top + panel_h)
        grid_top = panel[3] + gap * 1.6
        grid_bottom = height - m

        cols, rows = 6, len(LAYOUT)
        bw = (width - 2 * m - (cols - 1) * gap) / cols
        bh = (grid_bottom - grid_top - (rows - 1) * gap) / rows

        for ctrl in self.controls:
            if ctrl.pill:
                continue
            x1 = m + ctrl.col * (bw + gap)
            x2 = x1 + ctrl.span * bw + (ctrl.span - 1) * gap
            y1 = grid_top + ctrl.row * (bh + gap)
            ctrl.rect = (x1, y1, x2, y1 + bh)
            ctrl.depth = max(3.0, bh * 0.07)
            ctrl.radius = min(bw, bh) * 0.28
            size = min(bw, bh) * 0.34
            if len(ctrl.label) >= 4:
                size *= 0.78
            elif len(ctrl.label) == 3:
                size *= 0.90
            if ctrl.kind == "eq":
                size *= 1.25
            ctrl.px = max(10, int(size))

        mode_w = max(58.0, width * 0.14)
        theme_w = max(80.0, width * 0.20)
        self.mode_pill.rect = (width - m - mode_w, bar[1], width - m, bar[3])
        self.theme_pill.rect = (self.mode_pill.rect[0] - 8 - theme_w, bar[1],
                                self.mode_pill.rect[0] - 8, bar[3])
        for pill in (self.mode_pill, self.theme_pill):
            pill.depth = 0.0
            pill.radius = bar_h / 2
            pill.px = max(10, int(bar_h * 0.40))

        pad = panel_h * 0.10
        self.geom = {
            "w": width, "h": height, "m": m, "bar": bar, "panel": panel,
            "pad": pad, "panel_radius": min(28.0, panel_h * 0.16),
            "result_rect": (panel[0] + pad, panel[1] + panel_h * 0.58,
                            panel[2] - pad, panel[3]),
        }

    # -- drawing ----------------------------------------------------------------

    def on_resize(self, event):
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(30, self.redraw)

    def redraw(self):
        self._redraw_job = None
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        if w < 200 or h < 300:
            return
        th = self.theme
        c.delete("all")
        c.configure(bg=th["bg"][1])
        self.particles = []
        self.layout(w, h)
        g = self.geom

        def bg_at(y):
            return lerp_colour(th["bg"][0], th["bg"][1], y / h)

        # background: a gradient with two soft glowing orbs, drawn as one image
        self._bg_image = self.make_background(w, h)
        c.create_image(0, 0, image=self._bg_image, anchor="nw")

        # title: a little star and the name
        bx1, by1, bx2, by2 = g["bar"]
        mid_y = (by1 + by2) / 2
        star_r = (by2 - by1) * 0.34
        c.create_polygon(star_points(bx1 + star_r, mid_y, star_r, star_r * 0.38),
                         fill=th["accent"], outline="")
        c.create_text(bx1 + star_r * 2 + 8, mid_y, anchor="w", text="SCI·CALC",
                      fill=th["text"], font=self.font((by2 - by1) * 0.46, "bold"))

        # display panel with a soft glow
        px1, py1, px2, py2 = g["panel"]
        radius = g["panel_radius"]
        for i in range(4, 0, -1):
            grow = i * 3
            c.create_polygon(
                rounded_rect_points(px1 - grow, py1 - grow, px2 + grow, py2 + grow,
                                    radius + grow),
                smooth=True, outline="",
                fill=lerp_colour(bg_at((py1 + py2) / 2), th["edge"], 0.07 * (5 - i)))
        c.create_polygon(rounded_rect_points(px1, py1, px2, py2, radius), smooth=True,
                         fill=th["panel"], outline=th["edge"], width=2)

        self.ans_item = c.create_text(0, 0, anchor="nw", text="", fill=th["muted"])
        self.expr_item = c.create_text(0, 0, anchor="e", text="", fill=th["text"])
        self.result_item = c.create_text(0, 0, anchor="e", text="", fill=th["accent"])
        self.caret_item = c.create_line(0, 0, 0, 0, fill=th["accent"], width=2,
                                        capstyle="round")

        for ctrl in self.controls:
            self.draw_control(ctrl, bg_at)

        self.ready = True
        self.refresh_display()

    def make_background(self, w, h):
        """Build the background pixel by pixel at low resolution, then zoom it up.

        Doing it as one image (rather than stacked circles) keeps the gradient and
        the glows perfectly smooth, with no visible edges."""
        th = self.theme
        step = max(4, math.ceil(math.sqrt(w * h / 30000)))
        small_w, small_h = w // step + 1, h // step + 1
        top, bottom = _rgb(th["bg"][0]), _rgb(th["bg"][1])

        orbs = []
        for (colour_key, strength), (fx, fy, fr) in zip(th["orbs"], ORB_SPOTS):
            orbs.append((w * fx / step, h * fy / step, w * fr / step,
                         _rgb(th[colour_key]), strength))

        rows = []
        for j in range(small_h):
            t = min(1.0, j * step / h)
            base = [top[k] + (bottom[k] - top[k]) * t for k in range(3)]
            live = [(cx, radius, col, strength, (j - cy) ** 2)
                    for cx, cy, radius, col, strength in orbs
                    if abs(j - cy) < radius]
            row = []
            for i in range(small_w):
                r, g, b = base
                for cx, radius, col, strength, dy2 in live:
                    dist = math.sqrt((i - cx) ** 2 + dy2)
                    if dist < radius:
                        blend = strength * (1 - dist / radius) ** 1.6
                        r += (col[0] - r) * blend
                        g += (col[1] - g) * blend
                        b += (col[2] - b) * blend
                row.append("#%02x%02x%02x" % (int(r), int(g), int(b)))
            rows.append("{" + " ".join(row) + "}")

        small = tk.PhotoImage(width=small_w, height=small_h)
        small.put(" ".join(rows), to=(0, 0))
        return small.zoom(step, step)

    def draw_control(self, ctrl, bg_at):
        c = self.canvas
        th = self.theme
        face_colour, _ = th["kinds"][ctrl.kind]
        x1, y1, x2, y2 = ctrl.rect
        r, d = ctrl.radius, ctrl.depth

        if ctrl.kind == "eq":          # a permanent glow around the = button
            for i in (3, 2, 1):
                grow = i * 3
                c.create_polygon(
                    rounded_rect_points(x1 - grow, y1 - grow, x2 + grow, y2 + grow, r + grow),
                    smooth=True, outline="",
                    fill=lerp_colour(bg_at((y1 + y2) / 2), face_colour, 0.11 * (4 - i)))

        ctrl.shadow = None
        if d > 0:
            shadow_colour, amount = th["shadow"]
            ctrl.shadow = c.create_polygon(
                rounded_rect_points(x1, y1 + d, x2, y2, r), smooth=True, outline="",
                fill=lerp_colour(face_colour, shadow_colour, amount))
        ctrl.face = c.create_polygon(
            rounded_rect_points(x1, y1, x2, y2 - d, r), smooth=True,
            fill=face_colour, outline=face_colour, width=2)
        ctrl.text = c.create_text(
            (x1 + x2) / 2, (y1 + y2 - d) / 2, text=ctrl.label,
            font=self.font(ctrl.px, "bold"), fill=th["kinds"][ctrl.kind][1])
        self.paint(ctrl)

    def paint(self, ctrl):
        """Update one control's colours and position for its hover/pressed state."""
        if ctrl.face is None:
            return
        c = self.canvas
        th = self.theme
        face_colour, text_colour = th["kinds"][ctrl.kind]
        x1, y1, x2, y2 = ctrl.rect
        d = ctrl.depth

        colour = lerp_colour(face_colour, th["hover"], 0.26 * ctrl.hover)
        if ctrl.pill:
            outline = lerp_colour(th["edge"], th["accent"], ctrl.hover)
        else:
            outline = lerp_colour(face_colour, th["accent"], ctrl.hover)
        drop = 0.0
        if ctrl.pressed:
            colour = lerp_colour(colour, th["press"], 0.22)
            drop = d * 0.8

        c.coords(ctrl.face, *rounded_rect_points(
            x1, y1 + drop, x2, y2 - d + drop, ctrl.radius))
        c.itemconfigure(ctrl.face, fill=colour, outline=outline)
        c.coords(ctrl.text, (x1 + x2) / 2, (y1 + y2 - d) / 2 + drop)
        c.itemconfigure(ctrl.text, text=ctrl.label, fill=text_colour)

    def refresh_display(self):
        """Update the texts inside the display panel (cheap, no full redraw)."""
        if not self.ready:
            return
        c = self.canvas
        th = self.theme
        g = self.geom
        px1, py1, px2, py2 = g["panel"]
        pad = g["pad"]
        ph = py2 - py1
        max_width = (px2 - px1) - 2 * pad - 8

        # expression line
        if self.expr:
            text, px = self.fit_text(self.expr, max_width, ph * 0.19, 14, "normal", "end")
            colour = th["text"]
        else:
            text, px = "Type or tap" + self.ellipsis, int(ph * 0.12)
            colour = th["muted"]
        expr_y = py1 + ph * 0.45
        c.itemconfigure(self.expr_item, text=text, font=self.font(px), fill=colour)
        c.coords(self.expr_item, px2 - pad - 6, expr_y)
        caret_half = ph * 0.19 * 0.55
        c.coords(self.caret_item, px2 - pad, expr_y - caret_half, px2 - pad, expr_y + caret_half)
        c.itemconfigure(self.caret_item, fill=th["accent"],
                        state="normal" if self.caret_on else "hidden")

        # result line (pops when it arrives, shakes on errors)
        kind = self.result_kind
        if kind == "none":
            text = ""
        elif kind == "error":
            text = self.result_text
        else:
            text = "= " + self.result_text
        scale = 1 + 0.30 * (self.pop_frames / 10) ** 2 if self.pop_frames else 1.0
        text, px = self.fit_text(text, max_width, ph * 0.27 * scale, 13, "bold", "start")
        colour = {"preview": th["muted"], "final": th["accent"],
                  "error": th["error"]}.get(kind, th["muted"])
        shake = 0.0
        if self.shake_frames:
            shake = 10 * (self.shake_frames / 18) * math.sin(self.shake_frames * 1.3)
        c.itemconfigure(self.result_item, text=text, font=self.font(px, "bold"), fill=colour)
        c.coords(self.result_item, px2 - pad + shake, py1 + ph * 0.80)

        # little label in the corner
        if self.flash_msg:
            label, label_colour = self.flash_msg, th["accent"]
        elif self.has_ans:
            label, label_colour = "ANS  " + format_result(self.calc.ans), th["muted"]
        else:
            label, label_colour = "", th["muted"]
        c.itemconfigure(self.ans_item, text=label, fill=label_colour,
                        font=self.font(max(11, ph * 0.085), "bold"))
        c.coords(self.ans_item, px1 + pad, py1 + pad * 0.9)

        # top-bar pills show the current mode and theme
        self.mode_pill.label = self.calc.mode.upper()
        self.theme_pill.label = th["name"]
        self.paint(self.mode_pill)
        self.paint(self.theme_pill)

    # -- animation --------------------------------------------------------------

    def schedule_tick(self):
        if self._tick_job is None:
            self._tick_job = self.root.after(16, self._tick)

    def _tick(self):
        self._tick_job = None
        busy = False

        for ctrl in self.controls:
            target = 1.0 if (ctrl is self.hover_control or ctrl.pressed) else 0.0
            if abs(ctrl.hover - target) > 0.01:
                ctrl.hover += (target - ctrl.hover) * 0.35
                if abs(ctrl.hover - target) <= 0.01:
                    ctrl.hover = target
                self.paint(ctrl)
                busy = True

        if self.pop_frames or self.shake_frames:
            self.pop_frames = max(0, self.pop_frames - 1)
            self.shake_frames = max(0, self.shake_frames - 1)
            self.refresh_display()
            busy = True

        if self.particles:
            height = self.geom.get("h", 0)
            alive = []
            for p in self.particles:
                p["vy"] += 0.5
                p["x"] += p["vx"]
                p["y"] += p["vy"]
                p["size"] *= 0.955
                if p["size"] < 1.2 or p["y"] > height:
                    self.canvas.delete(p["id"])
                else:
                    s = p["size"]
                    self.canvas.coords(p["id"], p["x"] - s, p["y"] - s, p["x"] + s, p["y"] + s)
                    alive.append(p)
            self.particles = alive
            busy = busy or bool(alive)

        if busy:
            self.schedule_tick()

    def _blink(self):
        self.caret_on = not self.caret_on
        if self.ready and self.caret_item is not None:
            self.canvas.itemconfigure(
                self.caret_item, state="normal" if self.caret_on else "hidden")
        self.root.after(530, self._blink)

    def spawn_confetti(self):
        g = self.geom
        px1, py1, px2, py2 = g["panel"]
        origin_x = px2 - g["pad"] - 40
        origin_y = py1 + (py2 - py1) * 0.80
        th = self.theme
        palette = [th["accent"], th["accent2"], th["kinds"]["eq"][0],
                   th["kinds"]["op"][0], th["text"]]
        for _ in range(28):
            size = random.uniform(4, 9)
            shape = self.canvas.create_oval if random.random() < 0.5 else self.canvas.create_rectangle
            item = shape(origin_x - size, origin_y - size, origin_x + size, origin_y + size,
                         fill=random.choice(palette), outline="")
            self.particles.append({
                "id": item, "x": origin_x, "y": origin_y, "size": size,
                "vx": random.uniform(-8, 2), "vy": random.uniform(-11, -3),
            })
        self.schedule_tick()

    # -- mouse ------------------------------------------------------------------

    def control_at(self, x, y):
        for ctrl in self.controls:
            if ctrl.contains(x, y):
                return ctrl
        return None

    def on_motion(self, event):
        ctrl = self.control_at(event.x, event.y)
        if ctrl is not self.hover_control:
            self.hover_control = ctrl
            self.canvas.configure(cursor="hand2" if ctrl else "")
            self.schedule_tick()

    def on_leave(self, event):
        if self.hover_control is not None:
            self.hover_control = None
            self.canvas.configure(cursor="")
            self.schedule_tick()

    def on_mouse_down(self, event):
        ctrl = self.control_at(event.x, event.y)
        if ctrl is not None:
            ctrl.pressed = True
            self.active_control = ctrl
            self.schedule_tick()

    def on_mouse_up(self, event):
        ctrl, self.active_control = self.active_control, None
        if ctrl is not None:
            ctrl.pressed = False
            self.schedule_tick()
            if ctrl.contains(event.x, event.y):    # released on the same button
                self.dispatch(ctrl.action)
            return
        x1, y1, x2, y2 = self.geom.get("result_rect", (0, 0, 0, 0))
        if x1 <= event.x <= x2 and y1 <= event.y <= y2:
            self.copy_result()

    # -- keyboard ---------------------------------------------------------------

    def on_key(self, event):
        key = event.keysym
        if event.state & 0x4:                       # Ctrl held
            if key.lower() == "v":
                self.paste()
            elif key.lower() == "c":
                self.copy_result()
            return
        if key in ("Return", "KP_Enter") or event.char == "=":
            action = ":equals"
        elif key == "BackSpace":
            action = ":back"
        elif key in ("Escape", "Delete"):
            action = ":clear"
        elif is_typable(event.char):
            action = event.char
        else:
            return
        self.flash(action)
        self.dispatch(action)

    def flash(self, action):
        """Briefly press the on-screen button that matches a typed key."""
        for ctrl in self.controls:
            if ctrl.action == action:
                ctrl.pressed = True
                self.paint(ctrl)
                self.schedule_tick()
                self.root.after(100, lambda c=ctrl: self._release(c))
                return

    def _release(self, ctrl):
        ctrl.pressed = False
        self.schedule_tick()

    # -- the calculator's behaviour ---------------------------------------------

    def dispatch(self, action):
        if action == ":equals":
            self.equals()
        elif action == ":clear":
            self.clear()
        elif action == ":back":
            self.backspace()
        elif action == ":mode":
            self.toggle_mode()
        elif action == ":theme":
            self.next_theme()
        else:
            self.insert(action)

    def insert(self, text):
        if not text or (text == " " and (not self.expr or self.expr.endswith(" "))):
            return
        if self.just_evaluated:
            # After "=": an operator carries on from the answer, anything else starts fresh.
            self.just_evaluated = False
            self.expr = "ans" if text[0] in OPERATOR_STARTS else ""
        if len(self.expr) + len(text) > MAX_EXPRESSION_LENGTH:
            return
        self.expr += text
        self.update_preview()
        self.refresh_display()

    def backspace(self):
        self.just_evaluated = False
        # Delete a whole "sin(" style token in one go.
        match = re.search(r"[a-z][a-z0-9_]*\($", self.expr)
        self.expr = self.expr[:match.start()] if match else self.expr[:-1]
        self.update_preview()
        self.refresh_display()

    def clear(self):
        self.just_evaluated = False
        self.expr = ""
        self.result_text = ""
        self.result_kind = "none"
        self.refresh_display()

    def toggle_mode(self):
        self.calc.mode = "rad" if self.calc.mode == "deg" else "deg"
        self.update_preview()
        self.refresh_display()

    def next_theme(self):
        self.theme_index = (self.theme_index + 1) % len(THEMES)
        self.redraw()

    def equals(self):
        text = self.expr.strip()
        if not text:
            return
        try:
            value = self.calc.evaluate(text)
        except ValueError as error:
            self.result_text = str(error)
            self.result_kind = "error"
            self.shake_frames = 18
        else:
            self.result_text = format_result(value)
            self.result_kind = "final"
            self.has_ans = True
            self.just_evaluated = True
            self.pop_frames = 10
            if self.ready:
                self.spawn_confetti()
        self.refresh_display()
        self.schedule_tick()

    def update_preview(self):
        """Quietly work out the answer while typing; show nothing if it isn't valid yet."""
        text = self.expr.strip()
        if not text:
            self.result_text, self.result_kind = "", "none"
            return
        preview = Calculator(self.calc.mode)     # throwaway, so 'ans' is never touched
        preview.ans = self.calc.ans
        try:
            self.result_text = format_result(preview.evaluate(text))
            self.result_kind = "preview"
        except ValueError:
            self.result_text, self.result_kind = "", "none"

    def copy_result(self):
        if self.result_kind in ("preview", "final") and self.result_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.result_text)
            self.flash_msg = "Copied!"
            self.refresh_display()
            self.root.after(1200, self._clear_flash)

    def _clear_flash(self):
        self.flash_msg = ""
        self.refresh_display()

    def paste(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        text = "".join(ch for ch in text if is_typable(ch)).strip()
        if text:
            self.insert(text)


def main():
    scale = 1.0
    if sys.platform == "win32":
        try:                                    # crisp text on high-DPI Windows screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    root.title("Scientific Calculator")
    if sys.platform == "win32":
        scale = root.winfo_fpixels("1i") / 96
    root.geometry(f"{int(460 * scale)}x{int(760 * scale)}")
    root.minsize(int(380 * scale), int(640 * scale))
    FancyCalculator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
