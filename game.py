import os
import random
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty

FRAME_TIME = 0.05
SHOT_COOLDOWN = 0.22
DASH_COOLDOWN = 2.2
DASH_DISTANCE = 7
DASH_TRAIL_TTL = 0.18
PROJECTILE_SPEED = 2
POWERUP_SPAWN_INTERVAL = 8.0
POWERUP_LIFETIME = 14.0
SHOTGUN_DURATION = 10.0
DASH_BOOST_DURATION = 10.0
DASH_BOOST_COOLDOWN = 0.6
JUMP_DURATION = 0.45
CROUCH_GRACE = 0.12

LEVEL_CROUCH = 0
LEVEL_NORMAL = 1
LEVEL_JUMP = 2
LEVEL_NAMES = {LEVEL_CROUCH: "CROUCH", LEVEL_NORMAL: "NORMAL", LEVEL_JUMP: "JUMP"}
LEVEL_PLAYER_GLYPHS = {LEVEL_CROUCH: ".", LEVEL_NORMAL: "A", LEVEL_JUMP: "^"}
LEVEL_PLAYER2_GLYPHS = {LEVEL_CROUCH: ",", LEVEL_NORMAL: "B", LEVEL_JUMP: "M"}
LEVEL_PROJECTILE_GLYPHS = {LEVEL_CROUCH: ".", LEVEL_NORMAL: "*", LEVEL_JUMP: "O"}

ARENA_PRESETS = {
    "small": (42, 14),
    "medium": (56, 19),
    "large": (70, 24),
}

KEYMAP = {
    "p1": {
        "up": "w",
        "down": "s",
        "left": "a",
        "right": "d",
        "jump": "e",
        "crouch": "<shift>",
        "dash": "r",
        "shoot": "q",
    },
    "p2": {
        "up": "i",
        "down": "k",
        "left": "j",
        "right": "l",
        "jump": "o",
        "crouch": "h",
        "dash": "p",
        "shoot": "u",
    },
}


@dataclass
class Projectile:
    x: int
    y: int
    dx: int
    dy: int
    level: int
    owner: str


@dataclass
class PowerUp:
    x: int
    y: int
    kind: str
    spawned_at: float


@dataclass
class DashTrail:
    x: int
    y: int
    glyph: str
    expires_at: float


@dataclass
class Player:
    pid: str
    name: str
    x: int
    y: int
    level: int = LEVEL_NORMAL
    facing: Tuple[int, int] = (1, 0)
    alive: bool = True
    shield: bool = False
    shotgun_until: float = 0.0
    dash_boost_until: float = 0.0
    last_shot_at: float = -999.0
    last_dash_at: float = -999.0
    jump_until: float = 0.0
    crouch_until: float = 0.0

    def glyph(self) -> str:
        return LEVEL_PLAYER_GLYPHS[self.level] if self.pid == "p1" else LEVEL_PLAYER2_GLYPHS[self.level]

    def dash_cooldown(self, now: float) -> float:
        return DASH_BOOST_COOLDOWN if now < self.dash_boost_until else DASH_COOLDOWN

    def can_shoot(self, now: float) -> bool:
        return now - self.last_shot_at >= SHOT_COOLDOWN

    def can_dash(self, now: float) -> bool:
        return now - self.last_dash_at >= self.dash_cooldown(now)


class Keyboard:
    def __init__(self):
        self._fd = None
        self._old_settings = None

    def __enter__(self):
        if os.name != "nt":
            self._fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type, exc, tb):
        if os.name != "nt" and self._fd is not None and self._old_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)

    def get_keys(self) -> List[str]:
        keys: List[str] = []
        if os.name == "nt":
            while msvcrt.kbhit():
                c = msvcrt.getwch()
                if c in ("\x00", "\xe0"):
                    if msvcrt.kbhit():
                        scan = ord(msvcrt.getwch())
                        if scan in (42, 54, 160, 161):
                            keys.append("<shift>")
                    continue
                keys.append("\n" if c == "\r" else c.lower())
        else:
            while True:
                readable, _, _ = select.select([sys.stdin], [], [], 0)
                if not readable:
                    break
                c = sys.stdin.read(1)
                if not c:
                    break
                keys.append(c)
        return keys

    def wait_for_any_key(self):
        while True:
            if self.get_keys():
                return
            time.sleep(0.03)


def clear_screen():
    print("\033[2J\033[H", end="")


class AsciiArenaGame:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.projectiles: List[Projectile] = []
        self.powerups: List[PowerUp] = []
        self.dash_trails: List[DashTrail] = []
        self.last_spawn_at = time.time()
        self.scores = {"p1": 0, "p2": 0}
        self.bot_mode = False
        self.last_bot_action = 0.0
        self.arena_size_name = "large"
        self.arena_width, self.arena_height = ARENA_PRESETS[self.arena_size_name]

    def select_arena_size(self) -> bool:
        clear_screen()
        print("Choose arena size:\n")
        print("1) Small")
        print("2) Medium")
        print("3) Large")
        print("(Enter/Esc to cancel)")
        choice = input("\nSelect option: ").strip()
        if choice == "1":
            self.arena_size_name = "small"
        elif choice == "2":
            self.arena_size_name = "medium"
        elif choice == "3":
            self.arena_size_name = "large"
        else:
            return False
        self.arena_width, self.arena_height = ARENA_PRESETS[self.arena_size_name]
        return True

    def reset_round(self):
        self.players = {
            "p1": Player("p1", "P1", 4, self.arena_height // 2, facing=(1, 0)),
            "p2": Player(
                "p2",
                "BOT" if self.bot_mode else "P2",
                self.arena_width - 5,
                self.arena_height // 2,
                facing=(-1, 0),
            ),
        }
        self.projectiles = []
        self.powerups = []
        self.dash_trails = []
        self.last_spawn_at = time.time()

    def clamp_in_arena(self, x: int, y: int) -> Tuple[int, int]:
        return max(0, min(self.arena_width - 1, x)), max(0, min(self.arena_height - 1, y))

    def spawn_powerup_if_needed(self, now: float):
        if now - self.last_spawn_at < POWERUP_SPAWN_INTERVAL:
            return
        self.last_spawn_at = now
        occupied = {(p.x, p.y) for p in self.players.values()}
        for _ in range(30):
            x = random.randint(1, self.arena_width - 2)
            y = random.randint(1, self.arena_height - 2)
            if (x, y) not in occupied:
                self.powerups.append(PowerUp(x, y, random.choice(["shotgun", "dash_boost", "shield"]), now))
                return

    def apply_powerup(self, player: Player, kind: str, now: float):
        if kind == "shotgun":
            player.shotgun_until = max(player.shotgun_until, now + SHOTGUN_DURATION)
        elif kind == "dash_boost":
            player.dash_boost_until = max(player.dash_boost_until, now + DASH_BOOST_DURATION)
        elif kind == "shield":
            player.shield = True

    def handle_pickups(self, now: float):
        self.powerups = [p for p in self.powerups if now - p.spawned_at <= POWERUP_LIFETIME]
        for player in self.players.values():
            for pu in list(self.powerups):
                if (player.x, player.y) == (pu.x, pu.y):
                    self.apply_powerup(player, pu.kind, now)
                    self.powerups.remove(pu)

    def update_level_state(self, player: Player, now: float):
        if player.level == LEVEL_JUMP and now >= player.jump_until:
            player.level = LEVEL_NORMAL
        if player.level == LEVEL_CROUCH and now >= player.crouch_until:
            player.level = LEVEL_NORMAL

    def normalize_key(self, key: str) -> str:
        if key == "\x1b":
            return key
        if key in ("\x00", "\xe0"):
            return key
        if key.isalpha():
            return key.lower()
        if key == "\x10":  # Ctrl+P fallback sometimes emitted on odd terminals
            return "<shift>"
        return key

    def handle_key_for_player(self, player: Player, key: str, now: float):
        m = KEYMAP[player.pid]
        dx, dy = 0, 0
        if key == m["up"]:
            dy = -1
        elif key == m["down"]:
            dy = 1
        elif key == m["left"]:
            dx = -1
        elif key == m["right"]:
            dx = 1

        if dx or dy:
            player.facing = (dx, dy)
            player.x, player.y = self.clamp_in_arena(player.x + dx, player.y + dy)

        if key == m["jump"]:
            player.level = LEVEL_JUMP
            player.jump_until = now + JUMP_DURATION
        elif key == m["crouch"]:
            player.level = LEVEL_CROUCH
            player.crouch_until = now + CROUCH_GRACE
        elif key == m["dash"]:
            self.dash(player, now)
        elif key == m["shoot"]:
            self.shoot(player, now)

    def handle_inputs(self, keys: List[str], now: float):
        normalized = [self.normalize_key(k) for k in keys]
        if "\x1b" in normalized:
            raise KeyboardInterrupt

        for key in normalized:
            for player in self.players.values():
                if not player.alive:
                    continue
                if self.bot_mode and player.pid == "p2":
                    continue
                self.handle_key_for_player(player, key, now)

        for player in self.players.values():
            self.update_level_state(player, now)

    def run_bot(self, now: float):
        if not self.bot_mode:
            return
        bot = self.players["p2"]
        if not bot.alive or now - self.last_bot_action < 0.16:
            return
        self.last_bot_action = now
        action = random.choice(["move", "move", "move", "jump", "crouch", "dash", "shoot"])
        if action == "move":
            self.handle_key_for_player(bot, random.choice(["i", "j", "k", "l"]), now)
        elif action == "jump":
            self.handle_key_for_player(bot, "o", now)
        elif action == "crouch":
            self.handle_key_for_player(bot, "h", now)
        elif action == "dash":
            self.handle_key_for_player(bot, "p", now)
        elif action == "shoot":
            self.handle_key_for_player(bot, "u", now)
        self.update_level_state(bot, now)

    def shoot(self, player: Player, now: float):
        if not player.can_shoot(now):
            return
        player.last_shot_at = now
        dirs = [player.facing if player.facing != (0, 0) else (1, 0)]
        if now < player.shotgun_until:
            fx, fy = dirs[0]
            spread = [(fx, fy), (fx + fy, fy + fx), (fx - fy, fy - fx)]
            dirs = []
            for dx, dy in spread:
                ndx = 0 if dx == 0 else (1 if dx > 0 else -1)
                ndy = 0 if dy == 0 else (1 if dy > 0 else -1)
                if ndx == 0 and ndy == 0:
                    ndx = 1
                dirs.append((ndx, ndy))
        for dx, dy in dirs:
            self.projectiles.append(Projectile(player.x, player.y, dx, dy, player.level, player.pid))

    def dash(self, player: Player, now: float):
        if not player.can_dash(now):
            return
        player.last_dash_at = now
        dx, dy = player.facing
        if dx == 0 and dy == 0:
            dx = 1 if player.pid == "p1" else -1

        trail_glyph = "-" if dx != 0 else "|"
        start_x, start_y = player.x, player.y
        for i in range(1, DASH_DISTANCE):
            tx = start_x - dx * i
            ty = start_y - dy * i
            if 0 <= tx < self.arena_width and 0 <= ty < self.arena_height:
                self.dash_trails.append(DashTrail(tx, ty, trail_glyph, now + DASH_TRAIL_TTL))

        player.x, player.y = self.clamp_in_arena(player.x + dx * DASH_DISTANCE, player.y + dy * DASH_DISTANCE)

    def step_projectiles(self) -> Optional[str]:
        scorer = None
        for _ in range(PROJECTILE_SPEED):
            survivors = []
            for proj in self.projectiles:
                proj.x += proj.dx
                proj.y += proj.dy
                if not (0 <= proj.x < self.arena_width and 0 <= proj.y < self.arena_height):
                    continue
                hit = False
                for pid, player in self.players.items():
                    if pid == proj.owner or not player.alive:
                        continue
                    if (player.x, player.y, player.level) == (proj.x, proj.y, proj.level):
                        if player.shield:
                            player.shield = False
                        else:
                            player.alive = False
                            scorer = proj.owner
                        hit = True
                        break
                if not hit:
                    survivors.append(proj)
            self.projectiles = survivors
            if scorer:
                return scorer
        return None

    def step_dash_trails(self, now: float):
        self.dash_trails = [t for t in self.dash_trails if now < t.expires_at]

    def render(self, now: float):
        grid = [[" " for _ in range(self.arena_width)] for _ in range(self.arena_height)]

        for t in self.dash_trails:
            if 0 <= t.x < self.arena_width and 0 <= t.y < self.arena_height:
                grid[t.y][t.x] = t.glyph

        for pu in self.powerups:
            grid[pu.y][pu.x] = {"shotgun": "S", "dash_boost": "D", "shield": "H"}[pu.kind]
        for proj in self.projectiles:
            if 0 <= proj.x < self.arena_width and 0 <= proj.y < self.arena_height:
                grid[proj.y][proj.x] = LEVEL_PROJECTILE_GLYPHS[proj.level]
        for p in self.players.values():
            if p.alive:
                grid[p.y][p.x] = p.glyph()

        def status(player: Player) -> str:
            dash_left = max(0.0, player.dash_cooldown(now) - (now - player.last_dash_at))
            shot_left = max(0.0, SHOT_COOLDOWN - (now - player.last_shot_at))
            buffs = []
            if now < player.shotgun_until:
                buffs.append("SHOTGUN")
            if now < player.dash_boost_until:
                buffs.append("DASH+")
            if player.shield:
                buffs.append("SHIELD")
            return f"{player.name} LVL:{LEVEL_NAMES[player.level]:6} DASH:{dash_left:>4.1f}s SHOT:{shot_left:>4.2f}s BUFFS:{','.join(buffs) if buffs else '-'}"

        score_line = (
            f"ARENA:{self.arena_size_name.upper():6}  SCORE  P1:{self.scores['p1']}  "
            f"{self.players['p2'].name}:{self.scores['p2']}"
        )
        lines = [score_line, status(self.players["p1"]), "#" * (self.arena_width + 2)]
        for row in grid:
            lines.append("#" + "".join(row) + "#")
        lines.append("#" * (self.arena_width + 2))
        lines.append(status(self.players["p2"]))
        lines.append("ESC: menu | Dash leaves a short trail")

        clear_screen()
        print("\n".join(lines), flush=True)

    def show_point_popup(self, scorer_pid: str, kb: Keyboard):
        self.scores[scorer_pid] += 1
        winner_name = self.players[scorer_pid].name
        clear_screen()
        print(f"{winner_name} scored a point!\n")
        print(f"Current score: P1 {self.scores['p1']} - {self.players['p2'].name} {self.scores['p2']}")
        print("\nPress any key to continue...")
        kb.wait_for_any_key()

    def run_match(self, versus_bot: bool = False):
        self.bot_mode = versus_bot
        self.last_bot_action = 0.0
        self.reset_round()
        with Keyboard() as kb:
            try:
                while True:
                    now = time.time()
                    keys = kb.get_keys()
                    self.handle_inputs(keys, now)
                    self.run_bot(now)

                    self.spawn_powerup_if_needed(now)
                    self.handle_pickups(now)
                    scorer = self.step_projectiles()
                    self.step_dash_trails(now)

                    self.render(now)
                    if scorer:
                        self.show_point_popup(scorer, kb)
                        self.reset_round()
                    time.sleep(FRAME_TIME)
            except KeyboardInterrupt:
                return

    def show_controls(self):
        clear_screen()
        print("=== CONTROLS ===\n")
        print("P1: W/A/S/D move | E jump | LEFT SHIFT crouch | R dash | Q shoot")
        print("P2: I/J/K/L move | O jump | H crouch | P dash | U shoot")
        print("Jump auto-returns to normal level after a short time.")
        print("Crouch returns to normal when crouch key is no longer held/repeated.")
        print("Projectiles only hit opponents on the same vertical level.")
        print("\nPress Enter to return.")
        input()

    def show_powerups(self):
        clear_screen()
        print("=== POWERUPS ===\n")
        print("S = Shotgun (temporary): fires 3 projectiles in spread")
        print("D = Dash Boost (temporary): significantly lowers dash cooldown")
        print("H = Shield: blocks the next incoming bullet")
        print("\nPowerups spawn over time and expire if not picked up.")
        print("\nPress Enter to return.")
        input()

    def menu(self):
        while True:
            clear_screen()
            print(r"""
   ___   _____  _____ ___ ___   ___  _   _   _   _  ___
  / _ \ / ____|/ ____|_ _|_ _| / _ \| \ | | | \ | |/ _ \
 | | | | (___ | |     | | | | | | | |  \| | |  \| | | | |
 | | | |\___ \| |     | | | | | | | | . ` | | . ` | | | |
 | |_| |____) | |____ | | | | | |_| | |\  | | |\  | |_| |
  \___/|_____/ \_____|___|___| \___/|_| \_| |_| \_|\___/
""")
            print("ASCII 3-LAYER DUEL ARENA\n")
            print("1) 1v1 Local")
            print("2) Versus Bot")
            print("3) Controls")
            print("4) Powerups")
            print("5) Quit")
            choice = input("\nSelect option: ").strip()

            if choice in ("1", "2"):
                if self.select_arena_size():
                    self.run_match(versus_bot=choice == "2")
            elif choice == "3":
                self.show_controls()
            elif choice == "4":
                self.show_powerups()
            elif choice == "5":
                clear_screen()
                return


if __name__ == "__main__":
    AsciiArenaGame().menu()
