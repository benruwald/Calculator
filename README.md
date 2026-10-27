# Fancy Calculator

A scientific calculator with a hand-drawn, animated interface, written in pure
Python with tkinter. One file, no dependencies, and no `eval()`.

Everything on screen is drawn by hand on a tkinter Canvas: a gradient
background with glowing orbs, rounded 3D buttons that light up on hover and
squish when pressed, a glowing display with a blinking caret, confetti when you
press `=`, and four colour themes.

## Run it

```
python fancy_calculator.py
```

**Requirements:** Python 3.8 or newer with tkinter. The python.org installers
for Windows and macOS include it. On Debian/Ubuntu: `sudo apt install python3-tk`.

## What it can do

- **Full expressions** with correct precedence and brackets: `2 + 3 * (4 - 1)`
- **Operators:** `+ - * / % ^` (or `**`), factorial `5!`, scientific notation `1.5e3`
- **Functions:** `sqrt cbrt abs exp ln log log2 floor ceil`,
  `sin cos tan asin acos atan`, `sinh cosh tanh`
  (`log(x)` is base 10, `log(x, base)` picks the base)
- **Constants:** `pi`, `e`, `tau`, and `ans` (the previous result)
- **Degrees / radians** toggle for the trig functions
- **Live preview** of the answer while you type
- **Clear error messages** instead of crashes: divide by zero, `sqrt(-1)`,
  `171!`, missing brackets, unknown names, and so on

A few behaviours worth knowing:

- `-2^2` is `-4` and `2^3^2` is `2^9 = 512`, as in normal maths.
- After a result, typing an operator carries on from the answer (`+ 5` becomes
  `ans + 5`), while typing a number starts a fresh calculation.
- `tan(90)` in degrees mode is reported as undefined rather than a huge number.
- Floating-point noise is tidied, so `sin(180)` shows `0` and `0.1 + 0.2` shows `0.3`.

## Controls

| Input | Action |
| --- | --- |
| Click a button, or type | Enter an expression |
| `Enter` or `=` | Evaluate |
| `Backspace` | Delete the last character (a whole `sin(` at once) |
| `Esc` | Clear |
| `Ctrl+V` | Paste an expression |
| `Ctrl+C`, or click the result | Copy the result |
| `DEG` / `RAD` pill (top right) | Switch the angle mode |
| Theme pill (top right) | Cycle Neon, Candy, Ocean and Sunset |

## How it works

The file has two halves.

**1. The engine** is a tokenizer plus a recursive descent parser, with one
function per precedence level, so the grammar is directly visible in the code:

```
expression : term   (('+' | '-') term)*
term       : unary  (('*' | '/' | '%') unary)*
unary      : ('-' | '+') unary | power
power      : postfix ('^' unary)?
postfix    : primary '!'*
primary    : NUMBER | NAME | NAME '(' args ')' | '(' expression ')'
```

Sending the exponent through `unary` is what gives right-associative powers
and negative exponents (`2^-1`), and putting unary minus above `power` is what
makes `-2^2` come out as `-4`.

**2. The GUI** sits on top of the engine and draws everything onto a single
Canvas. Buttons are custom rounded shapes with eased hover and press
animations, the background is generated as one smooth image, and the layout is
computed from the window size, so it scales cleanly when you resize.

You can also use the engine without opening a window:

```python
from fancy_calculator import Calculator

calc = Calculator()
print(calc.evaluate("2 + 3 * (4 - 1)"))   # 11.0
```

## License

[MIT](LICENSE)
