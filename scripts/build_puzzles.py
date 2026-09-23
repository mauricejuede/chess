#!/usr/bin/env python3
"""Lädt Partien von chess.com, sucht mit Stockfish grobe Fehler und schreibt docs/puzzles.json.

Aufruf:
  python scripts/build_puzzles.py                 # Partien über die chess.com-API laden
  python scripts/build_puzzles.py --pgn datei.pgn # lokale PGN-Datei verwenden
"""
import argparse, hashlib, io, json, os, shutil, sys, time, urllib.request
from datetime import datetime, timezone

import chess, chess.engine, chess.pgn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = json.load(open(os.path.join(ROOT, "config.json")))
USER = CONFIG["username"].lower()
CACHE_PATH = os.path.join(ROOT, "data", "cache.json")
OUT_PATH = os.path.join(ROOT, "docs", "puzzles.json")

D_SCAN = CONFIG.get("scan_depth", 11)       # Tiefe für jede Stellung der Partie
D_PUZZLE = CONFIG.get("puzzle_depth", 14)   # Tiefe für die Puzzle-Stellungen
BLUNDER_CP = CONFIG.get("blunder_cp", 300)  # ab so vielen Centipawns Verlust gilt ein Zug als Patzer
UA = f"patzer-training (github; user {USER})"


# ---------- chess.com ----------
def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if attempt == 3:
                raise
            time.sleep(2 + attempt * 3)


def fetch_games():
    archives = http_json(f"https://api.chess.com/pub/player/{USER}/games/archives")["archives"]
    games = []
    for url in reversed(archives[-CONFIG.get("months", 3):]):
        for g in http_json(url).get("games", []):
            if g.get("rules") != "chess" or g.get("time_class") not in CONFIG["time_classes"]:
                continue
            if CONFIG.get("rated_only", True) and not g.get("rated", False):
                continue
            games.append(g["pgn"])
    return games


def read_pgn_file(path):
    out, f = [], open(path, encoding="utf-8")
    while True:
        g = chess.pgn.read_game(f)
        if g is None:
            break
        if g.headers.get("Event") == "Play vs Bot":
            continue
        out.append(str(g))
    return out


# ---------- engine helpers ----------
def cp(score, pov):
    s = score.pov(pov)
    m = s.mate()
    if m is not None:
        return (10000 - abs(m) * 10) * (1 if m > 0 else -1)
    return s.score()


def game_id(g):
    h = g.headers
    link = h.get("Link")
    if link:
        return link.rstrip("/").split("/")[-1]
    raw = "|".join(h.get(k, "") for k in ["Date", "EndTime", "White", "Black", "Result"])
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def plies_from(board, moves, evals=None):
    b, out = board.copy(), []
    for i, m in enumerate(moves):
        san = b.san(m)
        b.push(m)
        out.append({"u": m.uci(), "s": san, "f": b.fen(), "e": evals[i] if evals else None})
    return out


def eval_positions(eng, board, moves, depth):
    b, res = board.copy(), []
    for m in moves:
        b.push(m)
        if b.is_checkmate():
            res.append(-10000 if b.turn == chess.WHITE else 10000)
        elif b.is_game_over():
            res.append(0)
        else:
            res.append(cp(eng.analyse(b, chess.engine.Limit(depth=depth))["score"], chess.WHITE))
    return res


def analyse_game(eng, pgn_text):
    g = chess.pgn.read_game(io.StringIO(pgn_text))
    h = g.headers
    white = h["White"].lower() == USER
    if not white and h["Black"].lower() != USER:
        return None
    me = chess.WHITE if white else chess.BLACK
    moves = list(g.mainline_moves())
    start = g.board()
    e0 = cp(eng.analyse(start, chess.engine.Limit(depth=D_SCAN))["score"], chess.WHITE)
    evals = eval_positions(eng, start, moves, D_SCAN)
    gid = game_id(g)

    game = {
        "id": gid, "url": h.get("Link", ""), "start": start.fen(), "e0": e0,
        "plies": plies_from(start, moves, evals),
        "white": h["White"], "black": h["Black"], "res": h["Result"],
        "we": h.get("WhiteElo", "?"), "be": h.get("BlackElo", "?"),
        "term": h.get("Termination", ""), "date": h.get("UTCDate", h.get("Date", "")),
        "tc": h.get("TimeControl", ""),
    }

    puzzles, b = [], start.copy()
    for i, m in enumerate(moves):
        if b.turn == me:
            before = (e0 if i == 0 else evals[i - 1]) * (1 if white else -1)
            after = evals[i] * (1 if white else -1)
            if before - after >= BLUNDER_CP and before >= -250 and after < 100:
                p = build_puzzle(eng, b, m, white, gid, i, h)
                if p:
                    p["e0"] = e0 if i == 0 else evals[i - 1]
                    puzzles.append(p)
        b.push(m)
    return game, puzzles


def build_puzzle(eng, board, played, white, gid, ply, h):
    pov = board.turn
    legal = list(board.legal_moves)
    infos = eng.analyse(board, chess.engine.Limit(depth=D_PUZZLE), multipv=len(legal))
    moves = {}
    for inf in infos:
        pv = inf.get("pv", [])
        if not pv:
            continue
        u = pv[0]
        entry = {"s": board.san(u), "e": cp(inf["score"], pov)}
        if len(pv) > 1:
            b2 = board.copy(); b2.push(u)
            entry["r"] = pv[1].uci(); entry["rs"] = b2.san(pv[1])
        moves[u.uci()] = entry
    if played.uci() not in moves:
        return None
    best = max(moves, key=lambda k: moves[k]["e"])
    ev_best, ev_played = moves[best]["e"], moves[played.uci()]["e"]
    if ev_best - ev_played < BLUNDER_CP - 50 or ev_played >= 100:
        return None

    lim = chess.engine.Limit(depth=D_PUZZLE + 2)
    after = board.copy(); after.push(played)
    ref_pv = eng.analyse(after, lim).get("pv", [])[:9]
    ref_line = plies_from(board, [played] + ref_pv, eval_positions(eng, board, [played] + ref_pv, 11))
    bm = chess.Move.from_uci(best)
    b2 = board.copy(); b2.push(bm)
    best_pv = [bm] + eng.analyse(b2, lim).get("pv", [])[:7]
    best_line = plies_from(board, best_pv, eval_positions(eng, board, best_pv, 11))

    mate = None
    if abs(ev_played) >= 9000 and ev_played < 0:
        mate = round((10000 - abs(ev_played)) / 10)

    return {
        "id": f"{gid}-{ply}", "game": gid, "ply": ply,
        "date": h.get("UTCDate", h.get("Date", "")), "white": white,
        "opp": h["Black"] if white else h["White"], "moveNo": board.fullmove_number,
        "before": board.fen(), "played": played.uci(), "playedSan": board.san(played),
        "best": best, "bestSan": moves[best]["s"], "evBest": ev_best, "evPlayed": ev_played,
        "mate": mate, "moves": moves, "refLine": ref_line, "bestLine": best_line,
    }


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", help="lokale PGN-Datei statt chess.com-API")
    ap.add_argument("--engine", default=shutil.which("stockfish") or "/usr/games/stockfish")
    args = ap.parse_args()

    pgns = read_pgn_file(args.pgn) if args.pgn else fetch_games()
    pgns = pgns[: CONFIG.get("max_games", 100)] if not args.pgn else pgns
    print(f"{len(pgns)} Partien gefunden", flush=True)

    cache = json.load(open(CACHE_PATH)) if os.path.exists(CACHE_PATH) else {}
    eng = chess.engine.SimpleEngine.popen_uci(args.engine)
    eng.configure({"Threads": os.cpu_count() or 1})
    try:
        for n, pgn in enumerate(pgns, 1):
            gid = game_id(chess.pgn.read_game(io.StringIO(pgn)))
            if gid in cache:
                continue
            r = analyse_game(eng, pgn)
            if r:
                game, puzzles = r
                cache[gid] = {"game": game, "puzzles": puzzles}
                print(f"[{n}/{len(pgns)}] {gid}: {len(puzzles)} Puzzles", flush=True)
    finally:
        eng.quit()

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    json.dump(cache, open(CACHE_PATH, "w"), separators=(",", ":"))

    P, G = [], {}
    for entry in cache.values():
        if entry["puzzles"]:
            G[entry["game"]["id"]] = entry["game"]
            P.extend(entry["puzzles"])
    P.sort(key=lambda p: (p["date"], p["game"], p["ply"]), reverse=True)
    out = {"user": CONFIG["username"], "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "P": P, "G": G}
    json.dump(out, open(OUT_PATH, "w"), separators=(",", ":"))
    print(f"{len(P)} Puzzles aus {len(G)} Partien -> docs/puzzles.json")


if __name__ == "__main__":
    main()
