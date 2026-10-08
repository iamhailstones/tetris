import random
import uuid
from flask import Flask, jsonify, request, session

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
GAMES = {}


class Game:
    def __init__(self):
        self.board = [[0] * W for _ in range(H)]
        self.score = 0
        self.lines = 0
        self.over = False
        self.next = random.randint(1, 7)
        self.spawn()

    @property
    def level(self):
        return self.lines // 10 + 1

    @property
    def speed(self):
        return max(80, 800 - (self.level - 1) * 70)

    def spawn(self):
        self.kind = self.next
        self.next = random.randint(1, 7)
        self.shape = [row[:] for row in SHAPES[self.kind]]
        self.x = W // 2 - len(self.shape[0]) // 2
        self.y = 0
        if self.collides(self.shape, self.x, self.y):
            self.over = True

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
        """Returns True if the piece moved, False if it locked."""
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
        for cx, cy in self.cells(self.shape, self.x, self.y):
            if cy >= 0:
                self.board[cy][cx] = self.kind
        kept = [row for row in self.board if not all(row)]
        cleared = H - len(kept)
        if cleared:
            self.board = [[0] * W for _ in range(cleared)] + kept
            self.score += [0, 100, 300, 500, 800][cleared] * self.level
            self.lines += cleared
        self.spawn()

    def act(self, action):
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
    sid = uuid.uuid4().hex
    session["sid"] = sid
    GAMES[sid] = Game()
    return jsonify(GAMES[sid].state())


@app.post("/api/action")
def action():
    game = get_game()
    game.act((request.get_json(silent=True) or {}).get("action", ""))
    return jsonify(game.state())


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
         background:#14121f; color:#eee; font-family:Georgia, serif; }
  .wrap { display:flex; gap:24px; align-items:flex-start; padding:16px; }
  canvas { background:#0c0b14; border:3px solid #35305a; border-radius:6px; }
  .side { display:flex; flex-direction:column; gap:14px; min-width:140px; }
  .stat { font-size:1.05rem; }
  .stat b { display:block; font-size:1.5rem; }
  button { font:inherit; padding:8px 14px; border:0; border-radius:6px; background:#ffd54f; color:#222; cursor:pointer; }
  button:focus-visible { outline:3px solid #fff; outline-offset:2px; }
  .hint { opacity:.7; font-size:.85rem; line-height:1.5; }
</style>
</head>
<body>
<div class="wrap">
  <canvas id="board" width="300" height="600"></canvas>
  <div class="side">
    <canvas id="next" width="120" height="90"></canvas>
    <div class="stat">Score<b id="score">0</b></div>
    <div class="stat">Lines<b id="lines">0</b></div>
    <div class="stat">Level<b id="level">1</b></div>
    <button id="newBtn">New game</button>
    <button id="pauseBtn">Pause</button>
    <div class="hint">Left / Right: move<br>Up: rotate<br>Down: soft drop<br>Space: hard drop<br>P: pause</div>
  </div>
</div>

<script>
const COLORS = ["", "#4dd0e1", "#ffd54f", "#ba68c8", "#81c784", "#e57373", "#64b5f6", "#ffb74d"];
const CELL = 30;
const cv = document.getElementById("board"), ctx = cv.getContext("2d");
const nv = document.getElementById("next"), nctx = nv.getContext("2d");
let state = null, paused = false, seq = 0, applied = 0, timer = null;

async function api(path, body) {
  const mine = ++seq;
  const res = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})
  });
  const data = await res.json();
  if (mine >= applied) { applied = mine; state = data; render(); }
}

function block(c, x, y, size, color, alpha) {
  c.globalAlpha = alpha || 1;
  c.fillStyle = color;
  c.fillRect(x * size + 1, y * size + 1, size - 2, size - 2);
  c.globalAlpha = 1;
}

function render() {
  if (!state) return;
  ctx.clearRect(0, 0, cv.width, cv.height);
  state.board.forEach((row, y) => row.forEach((v, x) => { if (v) block(ctx, x, y, CELL, COLORS[v]); }));
  state.ghost.forEach(([x, y]) => block(ctx, x, y, CELL, COLORS[state.kind], 0.25));
  state.piece.forEach(([x, y]) => block(ctx, x, y, CELL, COLORS[state.kind]));

  nctx.clearRect(0, 0, nv.width, nv.height);
  state.next.forEach((row, r) => row.forEach((v, c) => { if (v) block(nctx, c + 0.5, r + 0.5, 25, COLORS[state.nextKind]); }));

  document.getElementById("score").textContent = state.score;
  document.getElementById("lines").textContent = state.lines;
  document.getElementById("level").textContent = state.level;

  if (state.over || paused) {
    ctx.fillStyle = "rgba(0,0,0,.65)";
    ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = "#fff";
    ctx.textAlign = "center";
    ctx.font = "30px Georgia";
    ctx.fillText(state.over ? "Game over" : "Paused", cv.width / 2, cv.height / 2);
  }
}

function schedule() {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    if (!paused && state && !state.over) await api("/api/action", {action: "tick"});
    schedule();
  }, state ? state.speed : 800);
}

function togglePause() { paused = !paused; render(); }

document.addEventListener("keydown", e => {
  const map = {ArrowLeft: "left", ArrowRight: "right", ArrowUp: "rotate", ArrowDown: "down", " ": "drop"};
  if (e.key.toLowerCase() === "p") { togglePause(); return; }
  if (map[e.key]) {
    e.preventDefault();
    if (!paused && state && !state.over) api("/api/action", {action: map[e.key]});
  }
});

document.getElementById("newBtn").onclick = async () => { paused = false; await api("/api/new"); };
document.getElementById("pauseBtn").onclick = togglePause;

api("/api/new").then(schedule);
</script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(debug=True)