# 🛡️ MiniChain: AI-Enhanced Persistent Blockchain Node
### **GSoC 2026 Proposal Prototype — AOSSIE / Stability Nexus**

MiniChain is a high-performance, minimalist blockchain node developed as a core prototype for the Google Summer of Code 2026 program. It is designed to demonstrate advanced concepts in **Distributed Ledgers**, **Asynchronous Processing**, and **AI-driven Network Security**.

---

## 🚀 Key Architectural Innovations

### 1. **Robust Persistence Layer (SQLite WAL)**
Unlike basic educational blockchains that store data in memory, MiniChain implements a professional-grade persistence engine using **SQLite 3 with Write-Ahead Logging (WAL)**. 
* **ACID Compliance:** Guarantees ledger integrity even in the event of hardware or software failure.
* **State vs. Ledger:** Separates block storage from the "World State" (balances/nonces) for O(1) account lookups.

### 2. **Sentinel AI (Heuristic Security Engine)**
A real-time security guard that monitors the mempool using statistical analysis before transactions are committed to the chain:
* **Anomaly Detection:** Uses **Z-score distribution analysis** to identify and flag transactions with suspicious amounts relative to historical network averages.
* **Anti-Spam Guard:** Implements a **sliding-window rate-limiting** mechanism to prevent DoS attacks by restricting transaction frequency per sender address.

### 3. **High-Throughput Async Validation**
Inspired by modern blockchains like Sui and Aptos, MiniChain utilizes Python's `asyncio` and `ThreadPoolExecutor` to perform **Parallel Signature Verification**. This architecture allows the node to verify multiple Ed25519 signatures concurrently, bypassing the Global Interpreter Lock (GIL) via C-level extensions.

### 4. **Professional Observability (Rich TUI)**
Features a live **Terminal User Interface (TUI)** built with the `Rich` library. It provides real-time metrics on:
* Chain Height and Total Supply.
* Live Mempool updates.
* Sentinel AI security logs with colored flagging (OK / ANOMALY / BLOCKED).

---

## 🛠️ Installation & Setup

### 1. Environment Setup
```bash
# Clone the repository
git clone [https://github.com/KDiamantidis/MiniChain-AOSSIE-GSoC.git](https://github.com/KDiamantidis/MiniChain-AOSSIE-GSoC.git)
cd MiniChain-AOSSIE-GSoC

# Create and activate virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install PyNaCl rich

### 2. Running the Node
```bash
# Initialize the database and Genesis block
python3 minichain.py init

# Generate your Ed25519 wallet
python3 minichain.py wallet-gen

# Launch the live monitor (Recommended: Keep open in a separate terminal)
python3 minichain.py monitor

# Submit a transaction
python3 minichain.py send --to <target_address> --amount 10


## 🕹️ CLI Command Reference
Command	    Description
init	    Resets the SQLite database and bootstraps a new Genesis block.
monitor	    Launches the live Rich TUI dashboard.
mine	    Executes the Proof-of-Work algorithm and commits the mempool to the ledger.
wallet-gen	Generates a new cryptographic keypair.
send	    Signs and submits a transfer. Supports --from-genesis for initial funding.
status	    Direct query of the World State and chain statistics.

##  🗺️ Roadmap (GSoC 2026 Implementation Plan)
[ ] Marabu Protocol Integration: Aligning the p2p networking layer with the official Stability Nexus/MiniChain standards.

[ ] Advanced ML Sentinel: Migrating from Z-score to an IsolationForest machine learning model for complex fraud detection.

[ ] State Sharding: Researching horizontal state partitioning to increase scalability.

Developer: Konstantinos Diamantidis

Position: Computer Science Student / GSoC 2026 Applicant

Organization: AOSSIE / Stability Nexus
