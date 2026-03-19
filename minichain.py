import argparse, asyncio, collections, hashlib, json, logging, math, sqlite3, struct, sys, time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

try:
    import nacl.signing, nacl.encoding
except ImportError: sys.exit("Error: pip install PyNaCl")
try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    _RICH = True
except ImportError: _RICH = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("minichain")

# Constants
DIFFICULTY, BLOCK_REWARD, GENESIS_SUPPLY, GENESIS_ADDR = 4, 50, 1_000_000, "genesis"
SENTINEL_Z_THRESH, SENTINEL_RATE_LIMIT, SENTINEL_WINDOW = 2.5, 5, 60.0
DB_PATH, WALLET_PATH = Path("minichain.db"), Path("wallet.key")

def blake2b_256(data: bytes) -> str: return hashlib.blake2b(data, digest_size=32).hexdigest()
def sha256_hash(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

class Wallet:
    def __init__(self, sk: nacl.signing.SigningKey) -> None:
        self._sk = sk; self._vk = sk.verify_key
    @classmethod
    def generate(cls): return cls(nacl.signing.SigningKey.generate())
    @classmethod
    def load(cls): return cls(nacl.signing.SigningKey(bytes.fromhex(WALLET_PATH.read_text().strip())))
    def save(self): WALLET_PATH.write_text(self._sk.encode(nacl.encoding.HexEncoder).decode())
    @property
    def address(self): return self._vk.encode(nacl.encoding.HexEncoder).decode()
    def sign(self, msg: bytes): return self._sk.sign(msg).signature

@dataclass
class Transaction:
    sender: str; receiver: str; amount: int; nonce: int
    signature: bytes = field(default=b""); contract_src: str = field(default="")
    def _payload(self): return f"{self.sender}|{self.receiver}|{self.amount}|{self.nonce}|{blake2b_256(self.contract_src.encode())}".encode()
    @property
    def txid(self): return blake2b_256(self._payload() + self.signature)
    def sign(self, w: Wallet): self.signature = w.sign(self._payload())
    def verify(self):
        try:
            vk = nacl.signing.VerifyKey(self.sender, encoder=nacl.encoding.HexEncoder)
            vk.verify(self._payload(), self.signature); return True
        except: return False
    def to_dict(self):
        d = self.__dict__.copy(); d["signature"] = self.signature.hex(); return d
    @classmethod
    def from_dict(cls, d):
        return cls(d["sender"], d["receiver"], d["amount"], d["nonce"], bytes.fromhex(d["signature"]), d.get("contract_src", ""))

@dataclass
class Block:
    index: int; timestamp: float; prev_hash: str; transactions: list; miner: str; nonce: int = 0
    current_hash: str = field(default="", init=False)
    def __post_init__(self): self.current_hash = self._compute_hash()
    def _compute_hash(self):
        tx_root = blake2b_256(json.dumps([t.to_dict() for t in self.transactions], sort_keys=True).encode())
        header = f"{self.index}|{self.timestamp:.6f}|{self.prev_hash}|{tx_root}|{self.miner}".encode()
        return sha256_hash(header + struct.pack(">Q", self.nonce))
    def mine(self, diff):
        target = "0" * diff
        while not self.current_hash.startswith(target):
            self.nonce += 1; self.current_hash = self._compute_hash()
    def to_dict(self):
        d = self.__dict__.copy(); d["transactions"] = [t.to_dict() for t in self.transactions]; return d
    @classmethod
    def from_dict(cls, d):
        txs = [Transaction.from_dict(t) for t in d["transactions"]]
        obj = cls(d["index"], d["timestamp"], d["prev_hash"], txs, d["miner"], d["nonce"])
        obj.current_hash = d["current_hash"]; return obj

class SentinelAI:
    def __init__(self):
        self._rate_window = collections.defaultdict(collections.deque)
        self._n, self._mean, self._M2 = 0, 0.0, 0.0
    def analyse(self, tx: Transaction):
        now = time.time(); win = self._rate_window[tx.sender]
        while win and (now - win[0]) > SENTINEL_WINDOW: win.popleft()
        win.append(now)
        if len(win) > SENTINEL_RATE_LIMIT: return "BLOCKED", 1.0, "Rate limit exceeded"
        std = math.sqrt(self._M2 / self._n) if self._n > 1 else 0.0
        z = abs(tx.amount - self._mean) / std if std > 0 else 0.0
        self._n += 1; delta = tx.amount - self._mean; self._mean += delta / self._n
        self._M2 += delta * (tx.amount - self._mean)
        return ("ANOMALY" if z > SENTINEL_Z_THRESH else "OK"), min(z/5.0, 1.0), f"Z-score: {z:.2f}"

class NodeDB:
    def __init__(self):
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS blocks (idx INTEGER PRIMARY KEY, hash TEXT, raw_json TEXT); CREATE TABLE IF NOT EXISTS state (address TEXT PRIMARY KEY, balance INTEGER, nonce INTEGER); CREATE TABLE IF NOT EXISTS mempool (txid TEXT PRIMARY KEY, raw_json TEXT, label TEXT, score REAL); CREATE TABLE IF NOT EXISTS logs (txid TEXT, label TEXT, score REAL, reason TEXT, ts REAL);")
    def apply_block(self, b: Block):
        with self.conn:
            self.conn.execute("INSERT INTO blocks VALUES (?,?,?)", (b.index, b.current_hash, json.dumps(b.to_dict())))
            self.conn.execute("INSERT INTO state VALUES (?,?,0) ON CONFLICT(address) DO UPDATE SET balance=balance+?", (b.miner, BLOCK_REWARD, BLOCK_REWARD))
            for tx in b.transactions:
                self.conn.execute("UPDATE state SET balance=balance-?, nonce=nonce+1 WHERE address=?", (tx.amount, tx.sender))
                self.conn.execute("INSERT INTO state VALUES (?,?,0) ON CONFLICT(address) DO UPDATE SET balance=balance+?", (tx.receiver, tx.amount, tx.amount))

class Blockchain:
    def __init__(self, db: NodeDB): self.db, self.ai = db, SentinelAI()
    def submit_tx(self, tx: Transaction):
        if not tx.verify(): return False, "Invalid Sig"
        label, score, reason = self.ai.analyse(tx)
        if label == "BLOCKED": return False, reason
        with self.db.conn:
            self.db.conn.execute("INSERT INTO mempool VALUES (?,?,?,?)", (tx.txid, json.dumps(tx.to_dict()), label, score))
            self.db.conn.execute("INSERT INTO logs VALUES (?,?,?,?,?)", (tx.txid, label, score, reason, time.time()))
        return True, label
    def mine(self, miner):
        rows = self.db.conn.execute("SELECT raw_json FROM mempool").fetchall()
        txs = [Transaction.from_dict(json.loads(r[0])) for r in rows]
        latest = Block.from_dict(json.loads(self.db.conn.execute("SELECT raw_json FROM blocks ORDER BY idx DESC LIMIT 1").fetchone()[0]))
        b = Block(latest.index + 1, time.time(), latest.current_hash, txs, miner)
        b.mine(DIFFICULTY); self.db.apply_block(b); self.db.conn.execute("DELETE FROM mempool"); return b

def main():
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init"); sub.add_parser("monitor"); sub.add_parser("mine"); sub.add_parser("wallet-gen")
    snd = sub.add_parser("send"); sub.add_parser("status")
    snd.add_argument("--to", required=True); snd.add_argument("--amount", type=int, required=True); snd.add_argument("--from-genesis", action="store_true")
    args = p.parse_args(); db = NodeDB(); bc = Blockchain(db)
    if args.cmd == "init":
        if DB_PATH.exists(): DB_PATH.unlink()
        db = NodeDB(); genesis = Block(0, 0.0, "0"*64, [], GENESIS_ADDR); db.apply_block(genesis)
        db.conn.execute("INSERT OR REPLACE INTO state VALUES (?,?,0)", (GENESIS_ADDR, GENESIS_SUPPLY))
        print("Chain Reset. Genesis:", genesis.current_hash)
    elif args.cmd == "wallet-gen":
        w = Wallet.generate(); w.save(); print("Address:", w.address)
    elif args.cmd == "monitor":
        console = Console(); l = Layout(); l.split_row(Layout(name="logs"), Layout(name="stats"))
        with Live(l, refresh_per_second=1, screen=True):
            while True:
                h = db.conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
                m = db.conn.execute("SELECT COUNT(*) FROM mempool").fetchone()[0]
                logs = db.conn.execute("SELECT * FROM logs ORDER BY ts DESC LIMIT 10").fetchall()
                t_stats = Table(box=box.SIMPLE); t_stats.add_row("Height", str(h)); t_stats.add_row("Mempool", str(m))
                l["stats"].update(Panel(t_stats, title="Stats", border_style="green"))
                t_logs = Table(box=box.SIMPLE, expand=True); t_logs.add_column("TxID"); t_logs.add_column("Label"); t_logs.add_column("Reason")
                for r in logs: t_logs.add_row(r["txid"][:12], r["label"], r["reason"])
                l["logs"].update(Panel(t_logs, title="Sentinel AI", border_style="cyan")); time.sleep(1)
    elif args.cmd == "send":
        if args.from_genesis:
            with db.conn: db.conn.execute("UPDATE state SET balance=balance-? WHERE address=?", (args.amount, GENESIS_ADDR))
            with db.conn: db.conn.execute("INSERT INTO state VALUES (?,?,0) ON CONFLICT(address) DO UPDATE SET balance=balance+?", (args.to, args.amount, args.amount))
            print("Done.")
        else:
            w = Wallet.load(); n = db.conn.execute("SELECT nonce FROM state WHERE address=?", (w.address,)).fetchone()[0]
            tx = Transaction(w.address, args.to, args.amount, n); tx.sign(w); ok, res = bc.submit_tx(tx); print(res)
    elif args.cmd == "mine":
        w = Wallet.load(); b = bc.mine(w.address); print("Mined:", b.current_hash)
    elif args.cmd == "status":
        res = db.conn.execute("SELECT * FROM state ORDER BY balance DESC").fetchall()
        print("\n--- World State (Current Balances) ---")
        for r in res:
            print(f"Address: {r['address'][:20]}... | Balance: {r['balance']} | Nonce: {r['nonce']}")
        
        blocks = db.conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]
        mempool = db.conn.execute("SELECT COUNT(*) FROM mempool").fetchone()[0]
        print(f"\nChain Height: {blocks} | Pending in Mempool: {mempool}\n")

if __name__ == "__main__": main()