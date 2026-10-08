import os
import random
import uuid
from flask import Flask, jsonify, request, session, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = "change-this-to-any-random-text"

W, H = 10, 20
SHAPES = {
    1: [[1, 1, 1, 1]],             # I
    2: [[1, 1], [1, 1]],           # O
    3: [[0, 1, 0], [1, 1, 1]],     # T
    4: [[0, 1, 1], [1, 1, 0]],     # S
    5: [[1, 1, 0], [0, 1, 1]],     # Z
    6: [[1, 0, 0], [1, 1, 1]],     # J
    7: [[0, 0, 1], [1, 1, 1]],     # L
}
# difficulty: (starting delay in ms, speed-up per level in ms, fastest allowed)
DIFFICULTY = {
    "easy":   (900, 50, 150),
    "normal": (800, 70, 80),
    "hard":   (450, 60, 50),
}
GAMES = {}


class Game:
    def __init__(self, difficulty="normal"):
        self.difficulty = difficulty if difficulty in DIFFICULTY else "normal"
        self.board = [[0] * W for _ in range(H)]
        self.score = 0
        self.lines = 0
        self.over = False
        self.event = ""        # "", "lock", "clear", "over"
        self.locked = []
        self.locked_kind = 0
        self.rows = []
        self.next = random.randint(1, 7)
        self.spawn()

    @property
    def level(self):
        return self.lines // 10 + 1

    @property
    def speed(self):
        start, step, fastest = DIFFICULTY[self.difficulty]
        return max(fastest, start - (self.level - 1) * step)

    def spawn(self):
        self.kind = self.next
        self.next = random.randint(1, 7)
        self.shape = [row[:] for row in SHAPES[self.kind]]
        self.x = W // 2 - len(self.shape[0]) // 2
        self.y = 0
        if self.collides(self.shape, self.x, self.y):
            self.over = True
            self.event = "over"

    def cells(self, shape, x, y):
        for r, row in enumerate(shape):
            for c, v in enumerate(row):
                if v:
                    yield x + c, y + r

    def collides(self, shape, x, y):
        for cx, cy in self.cells(shape, x, y):
            if cx < 0 or cx >= W or cy >= H:
                return True
            if cy >= 0 and self.board[cy][cx]:
                return True
        return False

    def move(self, dx):
        if not self.collides(self.shape, self.x + dx, self.y):
            self.x += dx

    def rotate(self):
        rotated = [list(row) for row in zip(*self.shape[::-1])]
        for kick in (0, -1, 1, -2, 2):
            if not self.collides(rotated, self.x + kick, self.y):
                self.shape, self.x = rotated, self.x + kick
                return

    def step_down(self):
        if not self.collides(self.shape, self.x, self.y + 1):
            self.y += 1
            return True
        self.lock()
        return False

    def hard_drop(self):
        dist = 0
        while not self.collides(self.shape, self.x, self.y + 1):
            self.y += 1
            dist += 1
        self.score += dist * 2
        self.lock()

    def lock(self):
        self.locked = [[x, y] for x, y in self.cells(self.shape, self.x, self.y)]
        self.locked_kind = self.kind
        self.event = "lock"
        for cx, cy in self.cells(self.shape, self.x, self.y):
            if cy >= 0:
                self.board[cy][cx] = self.kind
        self.rows = [i for i, row in enumerate(self.board) if all(row)]
        kept = [row for row in self.board if not all(row)]
        cleared = H - len(kept)
        if cleared:
            self.board = [[0] * W for _ in range(cleared)] + kept
            self.score += [0, 100, 300, 500, 800][cleared] * self.level
            self.lines += cleared
            self.event = "clear"
        self.spawn()

    def act(self, action):
        self.event = ""
        self.locked = []
        self.rows = []
        if self.over:
            return
        if action == "left":
            self.move(-1)
        elif action == "right":
            self.move(1)
        elif action == "rotate":
            self.rotate()
        elif action == "down":
            if self.step_down():
                self.score += 1
        elif action == "drop":
            self.hard_drop()
        elif action == "tick":
            self.step_down()

    def state(self):
        gy = self.y
        while not self.collides(self.shape, self.x, gy + 1):
            gy += 1
        return {
            "board": self.board,
            "piece": [[x, y] for x, y in self.cells(self.shape, self.x, self.y)],
            "ghost": [[x, y] for x, y in self.cells(self.shape, self.x, gy)],
            "kind": self.kind,
            "next": SHAPES[self.next],
            "nextKind": self.next,
            "score": self.score,
            "lines": self.lines,
            "level": self.level,
            "speed": self.speed,
            "over": self.over,
            "difficulty": self.difficulty,
            "event": self.event,
            "locked": self.locked,
            "lockedKind": self.locked_kind,
            "rows": self.rows,
        }


def get_game():
    sid = session.get("sid")
    if not sid or sid not in GAMES:
        sid = uuid.uuid4().hex
        session["sid"] = sid
        GAMES[sid] = Game()
    return GAMES[sid]


@app.post("/api/new")
def new_game():
    data = request.get_json(silent=True) or {}
    sid = uuid.uuid4().hex
    session["sid"] = sid
    GAMES[sid] = Game(data.get("difficulty", "normal"))
    return jsonify(GAMES[sid].state())


@app.post("/api/action")
def action():
    game = get_game()
    game.act((request.get_json(silent=True) or {}).get("action", ""))
    return jsonify(game.state())


@app.get("/bg.png")
def background():
    # Put your background picture next to app.py and name it bg.png
    return send_from_directory(BASE_DIR, "bg.png")


@app.get("/")
def index():
    return PAGE


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tetris</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background-color:#0e0c18;
         background-image:linear-gradient(rgba(8,7,14,.45), rgba(8,7,14,.7)), url('/bg.png');
         background-size:cover; background-position:center; background-repeat:no-repeat; background-attachment:fixed;
         color:#eee; font-family:Georgia, serif; }
  .wrap { display:flex; gap:24px; align-items:flex-start; padding:16px; }
  canvas { background:rgba(12,11,20,.78); border:3px solid #35305a; border-radius:10px; }
  .side { display:flex; flex-direction:column; gap:14px; min-width:170px; }
  .stat { font-size:1.05rem; text-shadow:0 1px 4px #000; }
  .stat b { display:block; font-size:1.5rem; }
  button { font:inherit; padding:8px 14px; border:0; border-radius:999px; background:#ffd54f; color:#222; cursor:pointer; }
  button:focus-visible { outline:3px solid #fff; outline-offset:2px; }
  .big { font-family:"Arial Black", Impact, "Trebuchet MS", sans-serif; font-weight:900;
         font-size:1.1rem; letter-spacing:1px; text-transform:uppercase; padding:12px 16px;
         background:linear-gradient(#ff8a65, #ff5252); color:#fff; box-shadow:0 4px 0 #b3261e; }
  .big:active { transform:translateY(3px); box-shadow:0 1px 0 #b3261e; }
  .diffs { display:flex; gap:6px; }
  .diff { flex:1; padding:7px 4px; background:#2c2745; color:#ddd; font-size:.9rem; }
  .diff.active { background:#ffd54f; color:#222; font-weight:bold; }
  .hint { opacity:.85; font-size:.85rem; line-height:1.5; text-shadow:0 1px 4px #000; }
</style>
</head>
<body>
<div class="wrap">
  <canvas id="board" width="300" height="600"></canvas>
  <div class="side">
    <canvas id="next" width="120" height="90"></canvas>
    <div class="diffs">
      <button class="diff" data-d="easy">Easy</button>
      <button class="diff" data-d="normal">Normal</button>
      <button class="diff" data-d="hard">Hard</button>
    </div>
    <div class="stat">Score<b id="score">0</b></div>
    <div class="stat">Highest score<b id="best">0</b></div>
    <div class="stat">Lines<b id="lines">0</b></div>
    <div class="stat">Level<b id="level">1</b></div>
    <button id="newBtn" class="big">New game</button>
    <button id="pauseBtn">Pause</button>
    <button id="soundBtn">Sound: on</button>
    <div class="hint">Left / Right: move<br>Up: rotate<br>Down: soft drop<br>Space: hard drop<br>P: pause</div>
  </div>
</div>

<script>
const COLORS = ["", "#4dd0e1", "#ffd54f", "#ba68c8", "#81c784", "#e57373", "#64b5f6", "#ffb74d"];
const CELL = 30;
const cv = document.getElementById("board"), ctx = cv.getContext("2d");
const nv = document.getElementById("next"), nctx = nv.getContext("2d");
let state = null, paused = false, seq = 0, applied = 0, timer = null;
let bubbles = [], soundOn = true, audio = null;

/* ---------- Difficulty and highest score (saved in this browser) ---------- */
function load(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; } }
function save(key, val) { try { localStorage.setItem(key, val); } catch (e) {} }

let diff = load("tetris_diff", "normal");
if (!["easy", "normal", "hard"].includes(diff)) diff = "normal";

function getBest() { return parseInt(load("tetris_best_" + diff, "0"), 10) || 0; }

function showBest() {
  const best = Math.max(getBest(), state ? state.score : 0);
  document.getElementById("best").textContent = best;
}

function checkBest(d) {
  if (d.score > getBest()) save("tetris_best_" + diff, d.score);
  showBest();
}

function markDiff() {
  document.querySelectorAll(".diff").forEach(b => b.classList.toggle("active", b.dataset.d === diff));
}

/* ---------- Sound (made with the browser, no files needed) ---------- */
function initAudio() {
  if (!audio) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audio = new AC();
  }
  if (audio && audio.state === "suspended") audio.resume();
}

function tone(freq, endFreq, dur, type, vol, delay) {
  if (!soundOn || !audio) return;
  const t = audio.currentTime + (delay || 0);
  const osc = audio.createOscillator(), gain = audio.createGain();
  osc.type = type || "sine";
  osc.frequency.setValueAtTime(freq, t);
  osc.frequency.exponentialRampToValueAtTime(endFreq, t + dur);
  gain.gain.setValueAtTime(vol || 0.15, t);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(gain); gain.connect(audio.destination);
  osc.start(t); osc.stop(t + dur);
}

const sounds = {
  move:   () => tone(300, 240, 0.05, "sine", 0.06),
  rotate: () => tone(350, 700, 0.09, "sine", 0.1),
  lock:   () => { tone(160, 60, 0.15, "triangle", 0.25); tone(500, 250, 0.08, "sine", 0.08); },
  clear:  () => [523, 659, 784, 1047].forEach((f, i) => tone(f, f * 1.02, 0.18, "sine", 0.14, i * 0.07)),
  over:   () => [400, 330, 260, 190].forEach((f, i) => tone(f, f * 0.9, 0.25, "triangle", 0.18, i * 0.15))
};

/* ---------- Bubbles ---------- */
function spawnBubbles(px, py, n, color) {
  for (let i = 0; i < n; i++) {
    bubbles.push({
      x: px + (Math.random() - 0.5) * CELL, y: py + (Math.random() - 0.5) * CELL,
      r: 3 + Math.random() * 7, vx: (Math.random() - 0.5) * 0.9,
      vy: -(0.4 + Math.random() * 1.3), life: 1, color: color
    });
  }
}

function handleEvent(d) {
  if (!d.event) return;
  if (d.event === "lock" || d.event === "clear") {
    sounds.lock();
    d.locked.forEach(([x, y]) => spawnBubbles(x * CELL + CELL / 2, y * CELL + CELL / 2, 4, COLORS[d.lockedKind]));
  }
  if (d.event === "clear") {
    sounds.clear();
    d.rows.forEach(r => { for (let x = 0; x < 10; x++) spawnBubbles(x * CELL + CELL / 2, r * CELL + CELL / 2, 3, "#ffffff"); });
  }
  if (d.event === "over") sounds.over();
}

/* ---------- Talking to Python ---------- */
async function api(path, body) {
  const mine = ++seq;
  const res = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})
  });
  const data = await res.json();
  handleEvent(data);
  if (mine >= applied) { applied = mine; state = data; checkBest(data); }
}

function newGame() {
  initAudio(); paused = false; bubbles = [];
  return api("/api/new", {difficulty: diff});
}

/* ---------- Drawing ---------- */
function block(c, x, y, size, color, alpha) {
  const cx = x * size + size / 2, cy = y * size + size / 2, r = size / 2 - 1;
  c.globalAlpha = alpha || 1;
  c.beginPath(); c.arc(cx, cy, r, 0, Math.PI * 2); c.fillStyle = color; c.fill();
  const g = c.createRadialGradient(cx - r * 0.35, cy - r * 0.4, r * 0.1, cx, cy, r);
  g.addColorStop(0, "rgba(255,255,255,0.75)");
  g.addColorStop(0.45, "rgba(255,255,255,0)");
  g.addColorStop(1, "rgba(0,0,0,0.35)");
  c.fillStyle = g; c.fill();
  c.strokeStyle = "rgba(255,255,255,0.45)"; c.lineWidth = 1; c.stroke();
  c.beginPath(); c.ellipse(cx - r * 0.3, cy - r * 0.4, r * 0.28, r * 0.16, -0.6, 0, Math.PI * 2);
  c.fillStyle = "rgba(255,255,255,0.8)"; c.fill();
  c.globalAlpha = 1;
}

function drawBubbles() {
  bubbles.forEach(b => {
    b.x += b.vx; b.y += b.vy; b.life -= 0.016;
    ctx.globalAlpha = Math.max(b.life, 0) * 0.8;
    ctx.beginPath(); ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,255,255,0.12)"; ctx.fill();
    ctx.strokeStyle = b.color; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.beginPath(); ctx.arc(b.x - b.r * 0.3, b.y - b.r * 0.3, b.r * 0.22, 0, Math.PI * 2);
    ctx.fillStyle = "#fff"; ctx.fill();
  });
  ctx.globalAlpha = 1;
  bubbles = bubbles.filter(b => b.life > 0);
}

function render() {
  ctx.clearRect(0, 0, cv.width, cv.height);
  nctx.clearRect(0, 0, nv.width, nv.height);
  if (state) {
    state.board.forEach((row, y) => row.forEach((v, x) => { if (v) block(ctx, x, y, CELL, COLORS[v]); }));
    state.ghost.forEach(([x, y]) => block(ctx, x, y, CELL, COLORS[state.kind], 0.25));
    state.piece.forEach(([x, y]) => block(ctx, x, y, CELL, COLORS[state.kind]));
    state.next.forEach((row, r) => row.forEach((v, c) => { if (v) block(nctx, c + 0.5, r + 0.5, 25, COLORS[state.nextKind]); }));

    document.getElementById("score").textContent = state.score;
    document.getElementById("lines").textContent = state.lines;
    document.getElementById("level").textContent = state.level;
  }
  drawBubbles();
  if (state && (state.over || paused)) {
    ctx.fillStyle = "rgba(0,0,0,.65)";
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = "#fff";
    ctx.textAlign = "center";
    ctx.font = "30px Georgia";
    ctx.fillText(state.over ? "Game over" : "Paused", cv.width / 2, cv.height / 2);
  }
  requestAnimationFrame(render);
}

/* ---------- Game timer and controls ---------- */
function schedule() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    if (!paused && state && !state.over) await api("/api/action", {action: "tick"});
    schedule();
  }, state ? state.speed : 800);
}

function togglePause() { paused = !paused; }

document.addEventListener("keydown", e => {
  initAudio();
  const map = {ArrowLeft: "left", ArrowRight: "right", ArrowUp: "rotate", ArrowDown: "down", " ": "drop"};
  if (e.key.toLowerCase() === "p") { togglePause(); return; }
  if (map[e.key]) {
    e.preventDefault();
    if (!paused && state && !state.over) {
      if (map[e.key] === "left" || map[e.key] === "right") sounds.move();
      if (map[e.key] === "rotate") sounds.rotate();
      api("/api/action", {action: map[e.key]});
    }
  }
});

document.querySelectorAll(".diff").forEach(b => {
  b.onclick = () => {
    diff = b.dataset.d;
    save("tetris_diff", diff);
    markDiff();
    b.blur();
    newGame();
  };
});
document.getElementById("newBtn").onclick = e => { e.target.blur(); newGame(); };
document.getElementById("pauseBtn").onclick = e => { e.target.blur(); togglePause(); };
document.getElementById("soundBtn").onclick = e => {
  initAudio(); soundOn = !soundOn;
  e.target.textContent = "Sound: " + (soundOn ? "on" : "off");
  e.target.blur();
};

markDiff();
showBest();
render();
newGame().then(schedule);
</script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(debug=True)