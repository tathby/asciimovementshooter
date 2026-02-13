import curses
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ARENA_WIDTH = 70
ARENA_HEIGHT = 24
FRAME_TIME = 0.05
SHOT_COOLDOWN = 0.22
DASH_COOLDOWN = 2.2
DASH_DISTANCE = 4
PROJECTILE_SPEED = 2
POWERUP_SPAWN_INTERVAL = 8.0
POWERUP_LIFETIME = 14.0
SHOTGUN_DURATION = 10.0
DASH_BOOST_DURATION = 10.0
DASH_BOOST_COOLDOWN = 0.6

LEVEL_CROUCH = 0
LEVEL_NORMAL = 1
LEVEL_JUMP = 2
LEVEL_NAMES = {LEVEL_CROUCH: "CROUCH", LEVEL_NORMAL: "NORMAL", LEVEL_JUMP: "JUMP"}
LEVEL_PLAYER_GLYPHS = {LEVEL_CROUCH: "·", LEVEL_NORMAL: "A", LEVEL_JUMP: "▲"}
LEVEL_PLAYER2_GLYPHS = {LEVEL_CROUCH: "•", LEVEL_NORMAL: "B", LEVEL_JUMP: "◆"}
LEVEL_PROJECTILE_GLYPHS = {LEVEL_CROUCH: ".", LEVEL_NORMAL: "*", LEVEL_JUMP: "O"}

KEYMAP = {
    "p1": {
        "up": ord("w"),
        "down": ord("s"),
        "left": ord("a"),
        "right": ord("d"),
        "jump": ord("r"),
        "crouch": ord("f"),
        "dash": ord("g"),
        "shoot": ord("t"),
    },
    "p2": {
        "up": ord("i"),
        "down": ord("k"),
        "left": ord("j"),
        "right": ord("l"),
        "jump": ord("u"),
        "crouch": ord("o"),
        "dash": ord("p"),
        "shoot": ord("y"),
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
class Player:
    pid: str
    name: str
    x: int
    y: int
    color: int
    level: int = LEVEL_NORMAL
    facing: Tuple[int, int] = (1, 0)
    alive: bool = True
    shield: bool = False
    shotgun_until: float = 0.0
    dash_boost_until: float = 0.0
    last_shot_at: float = -999.0
    last_dash_at: float = -999.0

    def glyph(self) -> str:
        return LEVEL_PLAYER_GLYPHS[self.level] if self.pid == "p1" else LEVEL_PLAYER2_GLYPHS[self.level]

    def dash_cooldown(self, now: float) -> float:
        return DASH_BOOST_COOLDOWN if now < self.dash_boost_until else DASH_COOLDOWN

    def can_shoot(self, now: float) -> bool:
        return now - self.last_shot_at >= SHOT_COOLDOWN

    def can_dash(self, now: float) -> bool:
        return now - self.last_dash_at >= self.dash_cooldown(now)


class AsciiArenaGame:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.players: Dict[str, Player] = {}
        self.projectiles: List[Projectile] = []
        self.powerups: List[PowerUp] = []
        self.last_spawn_at = time.time()
        self.winner: Optional[Player] = None

    def reset_round(self):
        self.players = {
            "p1": Player("p1", "P1", 8, ARENA_HEIGHT // 2, color=1, facing=(1, 0)),
            "p2": Player("p2", "P2", ARENA_WIDTH - 9, ARENA_HEIGHT // 2, color=2, facing=(-1, 0)),
        }
        self.projectiles = []
        self.powerups = []
        self.last_spawn_at = time.time()
        self.winner = None

    def draw_border(self):
        for x in range(ARENA_WIDTH + 2):
            self.stdscr.addch(1, x + 1, "#")
            self.stdscr.addch(ARENA_HEIGHT + 2, x + 1, "#")
        for y in range(ARENA_HEIGHT):
            self.stdscr.addch(y + 2, 1, "#")
            self.stdscr.addch(y + 2, ARENA_WIDTH + 2, "#")

    def to_screen(self, x: int, y: int) -> Tuple[int, int]:
        return y + 2, x + 2

    def clamp_in_arena(self, x: int, y: int) -> Tuple[int, int]:
        return max(0, min(ARENA_WIDTH - 1, x)), max(0, min(ARENA_HEIGHT - 1, y))

    def draw_hud(self, now: float):
        p1 = self.players["p1"]
        p2 = self.players["p2"]

        def player_status(p: Player) -> str:
            dash_ready = max(0.0, p.dash_cooldown(now) - (now - p.last_dash_at))
            shot_ready = max(0.0, SHOT_COOLDOWN - (now - p.last_shot_at))
            buffs = []
            if now < p.shotgun_until:
                buffs.append("SHOTGUN")
            if now < p.dash_boost_until:
                buffs.append("DASH+")
            if p.shield:
                buffs.append("SHIELD")
            buff_text = ",".join(buffs) if buffs else "-"
            return (
                f"{p.name} LVL:{LEVEL_NAMES[p.level]:6} DASH:{dash_ready:>4.1f}s "
                f"SHOT:{shot_ready:>4.2f}s BUFFS:{buff_text}"
            )

        self.stdscr.addstr(0, 2, player_status(p1)[:ARENA_WIDTH + 1], curses.color_pair(1))
        self.stdscr.addstr(ARENA_HEIGHT + 3, 2, player_status(p2)[:ARENA_WIDTH + 1], curses.color_pair(2))

    def spawn_powerup_if_needed(self, now: float):
        if now - self.last_spawn_at < POWERUP_SPAWN_INTERVAL:
            return
        self.last_spawn_at = now
        occupied = {(p.x, p.y) for p in self.players.values()}
        tries = 0
        while tries < 30:
            x = random.randint(2, ARENA_WIDTH - 3)
            y = random.randint(2, ARENA_HEIGHT - 3)
            if (x, y) not in occupied:
                kind = random.choice(["shotgun", "dash_boost", "shield"])
                self.powerups.append(PowerUp(x, y, kind, now))
                break
            tries += 1

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
                if player.x == pu.x and player.y == pu.y:
                    self.apply_powerup(player, pu.kind, now)
                    self.powerups.remove(pu)

    def draw_powerups(self):
        glyphs = {"shotgun": "S", "dash_boost": "D", "shield": "H"}
        for pu in self.powerups:
            sy, sx = self.to_screen(pu.x, pu.y)
            self.stdscr.addstr(sy, sx, glyphs[pu.kind], curses.color_pair(3))

    def handle_movement_key(self, player: Player, key: int):
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
        elif key == m["crouch"]:
            player.level = LEVEL_CROUCH

    def shoot(self, player: Player, now: float):
        if not player.can_shoot(now):
            return
        player.last_shot_at = now
        dirs = [player.facing]
        if dirs[0] == (0, 0):
            dirs = [(1, 0)]
        if now < player.shotgun_until:
            fx, fy = dirs[0]
            dirs = [(fx, fy), (fx + fy, fy + fx), (fx - fy, fy - fx)]
            normalized = []
            for dx, dy in dirs:
                ndx = 0 if dx == 0 else (1 if dx > 0 else -1)
                ndy = 0 if dy == 0 else (1 if dy > 0 else -1)
                if ndx == 0 and ndy == 0:
                    ndx = 1
                normalized.append((ndx, ndy))
            dirs = normalized
        for dx, dy in dirs:
            self.projectiles.append(Projectile(player.x, player.y, dx, dy, player.level, player.pid))

    def dash(self, player: Player, now: float):
        if not player.can_dash(now):
            return
        player.last_dash_at = now
        dx, dy = player.facing
        if dx == 0 and dy == 0:
            dx = 1 if player.pid == "p1" else -1
        player.x, player.y = self.clamp_in_arena(player.x + dx * DASH_DISTANCE, player.y + dy * DASH_DISTANCE)

    def process_key(self, key: int, now: float):
        for player in self.players.values():
            if not player.alive:
                continue
            m = KEYMAP[player.pid]
            self.handle_movement_key(player, key)
            if key == m["dash"]:
                self.dash(player, now)
            if key == m["shoot"]:
                self.shoot(player, now)

        if key == ord("v"):
            self.players["p1"].level = LEVEL_NORMAL
        if key == ord("m"):
            self.players["p2"].level = LEVEL_NORMAL

    def step_projectiles(self):
        for _ in range(PROJECTILE_SPEED):
            survivors = []
            for proj in self.projectiles:
                proj.x += proj.dx
                proj.y += proj.dy
                if not (0 <= proj.x < ARENA_WIDTH and 0 <= proj.y < ARENA_HEIGHT):
                    continue

                hit = False
                for pid, player in self.players.items():
                    if pid == proj.owner or not player.alive:
                        continue
                    if player.x == proj.x and player.y == proj.y and player.level == proj.level:
                        if player.shield:
                            player.shield = False
                        else:
                            player.alive = False
                            self.winner = self.players[proj.owner]
                        hit = True
                        break
                if not hit:
                    survivors.append(proj)
            self.projectiles = survivors

    def draw_entities(self):
        for proj in self.projectiles:
            sy, sx = self.to_screen(proj.x, proj.y)
            owner_color = 1 if proj.owner == "p1" else 2
            self.stdscr.addstr(sy, sx, LEVEL_PROJECTILE_GLYPHS[proj.level], curses.color_pair(owner_color))

        for player in self.players.values():
            if not player.alive:
                continue
            sy, sx = self.to_screen(player.x, player.y)
            self.stdscr.addstr(sy, sx, player.glyph(), curses.color_pair(player.color) | curses.A_BOLD)

    def menu_screen(self) -> str:
        selection = 0
        options = ["Start Match", "Controls", "Powerups", "Quit"]
        while True:
            self.stdscr.erase()
            title = [
                r"   ___   _____  _____ ___ ___   ___  _   _   _   _  ___  ",
                r"  / _ \ / ____|/ ____|_ _|_ _| / _ \| \ | | | \ | |/ _ \ ",
                r" | | | | (___ | |     | | | | | | | |  \| | |  \| | | | |",
                r" | | | |\___ \| |     | | | | | | | | . ` | | . ` | | | |",
                r" | |_| |____) | |____ | | | | | |_| | |\  | | |\  | |_| |",
                r"  \___/|_____/ \_____|___|___| \___/|_| \_| |_| \_|\___/ ",
            ]
            y = 2
            for line in title:
                self.stdscr.addstr(y, 4, line, curses.color_pair(3))
                y += 1
            self.stdscr.addstr(y + 1, 8, "ASCII 3-LAYER DUEL ARENA", curses.A_BOLD)
            for idx, option in enumerate(options):
                marker = ">" if idx == selection else " "
                self.stdscr.addstr(y + 4 + idx, 12, f"{marker} {idx + 1}. {option}")
            self.stdscr.addstr(y + 10, 8, "Use ↑/↓ or 1-4. Enter to select.")
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key in (curses.KEY_UP, ord("w")):
                selection = (selection - 1) % len(options)
            elif key in (curses.KEY_DOWN, ord("s")):
                selection = (selection + 1) % len(options)
            elif key in (ord("1"), ord("2"), ord("3"), ord("4")):
                selection = int(chr(key)) - 1
                return options[selection]
            elif key in (10, 13):
                return options[selection]

    def info_screen(self, title: str, lines: List[str]):
        while True:
            self.stdscr.erase()
            self.stdscr.addstr(2, 4, title, curses.A_BOLD)
            y = 4
            for line in lines:
                self.stdscr.addstr(y, 6, line)
                y += 1
            self.stdscr.addstr(y + 2, 6, "Press ESC or Enter to return to menu.")
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key in (27, 10, 13):
                return

    def run_match(self):
        self.reset_round()
        self.stdscr.nodelay(True)
        self.stdscr.timeout(0)

        while True:
            now = time.time()
            key = self.stdscr.getch()
            while key != -1:
                if 65 <= key <= 90:
                    key += 32
                if key == 27:
                    return
                self.process_key(key, now)
                key = self.stdscr.getch()

            self.spawn_powerup_if_needed(now)
            self.handle_pickups(now)
            self.step_projectiles()

            if not self.players["p1"].alive:
                self.winner = self.players["p2"]
            elif not self.players["p2"].alive:
                self.winner = self.players["p1"]

            self.stdscr.erase()
            self.draw_hud(now)
            self.draw_border()
            self.draw_powerups()
            self.draw_entities()
            self.stdscr.addstr(ARENA_HEIGHT + 5, 2, "ESC back to menu | P1 reset level: V | P2 reset level: M")
            self.stdscr.refresh()

            if self.winner:
                self.round_over_screen()
                return
            time.sleep(FRAME_TIME)

    def round_over_screen(self):
        while True:
            self.stdscr.erase()
            self.stdscr.addstr(8, 10, f"{self.winner.name} WINS! ONE SHOT, ONE LIFE.", curses.A_BOLD)
            self.stdscr.addstr(10, 10, "Press Enter for menu or R for rematch.")
            self.stdscr.refresh()
            key = self.stdscr.getch()
            if key in (10, 13):
                return
            if key in (ord("r"), ord("R")):
                self.run_match()
                return

    def run(self):
        while True:
            choice = self.menu_screen()
            if choice == "Start Match":
                self.run_match()
            elif choice == "Controls":
                self.info_screen(
                    "CONTROLS",
                    [
                        "P1 Move: W/A/S/D | Jump: R | Crouch: F | Shoot: T | Dash: G | Level Normal: V",
                        "P2 Move: I/J/K/L | Jump: U | Crouch: O | Shoot: Y | Dash: P | Level Normal: M",
                        "Projectiles only hit enemies on the SAME vertical level.",
                        "Jump/Crouch changes glyph size to simulate height.",
                        "Dash has cooldown shown in HUD. Shooting has anti-spam cooldown.",
                    ],
                )
            elif choice == "Powerups":
                self.info_screen(
                    "POWERUPS",
                    [
                        "S = Shotgun (temporary): fires 3 projectiles in a spread.",
                        "D = Dash Boost (temporary): drastically reduces dash cooldown.",
                        "H = Shield: blocks exactly one incoming bullet.",
                        "Powerups spawn over time and disappear if unclaimed.",
                    ],
                )
            elif choice == "Quit":
                return


def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_MAGENTA, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)

    game = AsciiArenaGame(stdscr)
    game.run()


if __name__ == "__main__":
    curses.wrapper(main)
