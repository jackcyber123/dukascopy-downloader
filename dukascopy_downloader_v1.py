import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import date, datetime, timezone
from pathlib import Path
import threading, queue, os, csv, urllib.request, urllib.error, calendar, struct, lzma

APP = "Dukascopy Historical Data Downloader V1"

SYMBOLS = [
    "BTCUSD","EURUSD","GBPUSD","USDJPY","USDCHF","USDCAD","AUDUSD","NZDUSD",
    "EURGBP","EURJPY","GBPJPY","XAUUSD","XAGUSD","US30","US500",
    "DEUIDXEUR","UK100GBP","JPNIDXJPY"
]

# Common price scales used by Dukascopy feed. Unknown symbols can be entered
# manually in the Price scale box.
SCALES = {
    "BTCUSD": 1000.0,
    "XAUUSD": 1000.0, "XAGUSD": 1000.0,
    "EURUSD": 100000.0, "GBPUSD": 100000.0, "USDCHF": 100000.0,
    "USDCAD": 100000.0, "AUDUSD": 100000.0, "NZDUSD": 100000.0,
    "EURGBP": 100000.0, "EURJPY": 1000.0, "GBPJPY": 1000.0,
    "USDJPY": 1000.0, "US30": 10.0, "US500": 10.0,
    "DEUIDXEUR": 10.0, "UK100GBP": 10.0, "JPNIDXJPY": 10.0
}

def duka_url(symbol, y, m, d, h):
    return f"https://datafeed.dukascopy.com/datafeed/{symbol.lower()}/{y}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"

def decode_bi5(data):
    raw = lzma.decompress(data)
    if len(raw) % 20:
        raise ValueError("Unexpected BI5 record length")
    rows = []
    for i in range(0, len(raw), 20):
        rows.append(struct.unpack(">iiiii", raw[i:i+20]))
    return rows

class App:
    def __init__(self, root):
        self.root = root
        root.title(APP)
        root.geometry("850x680")
        root.minsize(780, 620)
        self.q = queue.Queue()
        self.stop_flag = False

        f = ttk.Frame(root, padding=12)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text=APP, font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        ttk.Label(f, text="Symbol").grid(row=1, column=0, sticky="w")
        self.symbol = ttk.Combobox(f, values=SYMBOLS, width=20)
        self.symbol.set("BTCUSD")
        self.symbol.grid(row=1, column=1, sticky="w", padx=8)

        ttk.Label(f, text="Data").grid(row=1, column=2, sticky="e")
        self.dtype = ttk.Combobox(f, values=["Tick"], state="readonly", width=18)
        self.dtype.set("Tick")
        self.dtype.grid(row=1, column=3, sticky="w", padx=8)

        ttk.Label(f, text="From (YYYY-MM-DD)").grid(row=2, column=0, sticky="w", pady=6)
        self.start = ttk.Entry(f, width=20)
        self.start.insert(0, "2020-01-01")
        self.start.grid(row=2, column=1, sticky="w", padx=8)

        ttk.Label(f, text="To (YYYY-MM-DD)").grid(row=2, column=2, sticky="e")
        self.end = ttk.Entry(f, width=20)
        self.end.insert(0, str(date.today()))
        self.end.grid(row=2, column=3, sticky="w", padx=8)

        ttk.Label(f, text="Price side").grid(row=3, column=0, sticky="w")
        self.side = ttk.Combobox(f, values=["Bid", "Ask", "Bid + Ask"],
                                 state="readonly", width=20)
        self.side.set("Bid + Ask")
        self.side.grid(row=3, column=1, sticky="w", padx=8)

        ttk.Label(f, text="Price scale").grid(row=3, column=2, sticky="e")
        self.scale = ttk.Entry(f, width=20)
        self.scale.insert(0, "Auto")
        self.scale.grid(row=3, column=3, sticky="w", padx=8)

        ttk.Label(f, text="Output folder").grid(row=4, column=0, sticky="w", pady=6)
        self.out = ttk.Entry(f, width=56)
        self.out.insert(0, str(Path.home() / "DukascopyData"))
        self.out.grid(row=4, column=1, columnspan=2, sticky="ew", padx=8)
        ttk.Button(f, text="Browse", command=self.browse).grid(row=4, column=3, sticky="w")

        self.skip = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Resume / skip existing chunks",
                        variable=self.skip).grid(row=5, column=0, columnspan=2, sticky="w")

        self.progress = ttk.Progressbar(f, mode="determinate")
        self.progress.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(15, 5))
        self.status = ttk.Label(f, text="Ready.")
        self.status.grid(row=7, column=0, columnspan=4, sticky="w")

        buttons = ttk.Frame(f)
        buttons.grid(row=8, column=0, columnspan=4, sticky="w", pady=8)
        self.go = ttk.Button(buttons, text="DOWNLOAD", command=self.start_download)
        self.go.pack(side="left")
        self.stop = ttk.Button(buttons, text="STOP", command=self.stop_download, state="disabled")
        self.stop.pack(side="left", padx=8)

        ttk.Label(f, text="Log").grid(row=9, column=0, sticky="w")
        self.log = tk.Text(f, height=20, wrap="none")
        self.log.grid(row=10, column=0, columnspan=4, sticky="nsew")
        sb = ttk.Scrollbar(f, orient="vertical", command=self.log.yview)
        sb.grid(row=10, column=4, sticky="ns")
        self.log.configure(yscrollcommand=sb.set)

        f.columnconfigure(3, weight=1)
        f.rowconfigure(10, weight=1)
        root.after(100, self.poll)

    def browse(self):
        p = filedialog.askdirectory()
        if p:
            self.out.delete(0, "end")
            self.out.insert(0, p)

    def start_download(self):
        try:
            s = date.fromisoformat(self.start.get().strip())
            e = date.fromisoformat(self.end.get().strip())
            if e < s:
                raise ValueError
        except Exception:
            messagebox.showerror("Date error", "Use YYYY-MM-DD and ensure To >= From.")
            return

        sym = self.symbol.get().strip().upper()
        if not sym:
            messagebox.showerror("Symbol error", "Enter a symbol.")
            return

        self.stop_flag = False
        self.go.config(state="disabled")
        self.stop.config(state="normal")
        self.progress["value"] = 0

        args = (sym, s, e, self.side.get(), self.scale.get().strip(),
                Path(self.out.get().strip()), self.skip.get())
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def stop_download(self):
        self.stop_flag = True
        self.write("STOP requested. Finishing current chunk...")

    def write(self, msg):
        self.q.put(("log", msg))

    def worker(self, sym, start, end, side, scale_text, out, skip):
        out.mkdir(parents=True, exist_ok=True)
        total_days = (end - start).days + 1
        done_days = 0
        failed = []
        day = start

        while day <= end and not self.stop_flag:
            daydir = out / sym / "TICK" / day.strftime("%Y") / day.strftime("%m") / day.strftime("%d")
            daydir.mkdir(parents=True, exist_ok=True)

            for hour in range(24):
                if self.stop_flag:
                    break

                target = daydir / f"{hour:02d}.csv"
                if skip and target.exists() and target.stat().st_size > 0:
                    self.write(f"SKIP  {day} {hour:02d}:00")
                    continue

                url = duka_url(sym, day.year, day.month, day.day, hour)
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        data = resp.read()

                    if not data:
                        self.write(f"EMPTY {day} {hour:02d}:00")
                        continue

                    rows = decode_bi5(data)
                    scale = SCALES.get(sym) if scale_text.lower() == "auto" else float(scale_text)
                    if not scale:
                        raise ValueError("Unknown Auto scale. Enter a numeric price scale.")

                    base = calendar.timegm((day.year, day.month, day.day, hour, 0, 0))
                    with target.open("w", newline="", encoding="utf-8") as fh:
                        w = csv.writer(fh)
                        if side == "Bid":
                            w.writerow(["timestamp_utc", "bid", "bid_volume"])
                        elif side == "Ask":
                            w.writerow(["timestamp_utc", "ask", "ask_volume"])
                        else:
                            w.writerow(["timestamp_utc", "bid", "ask", "bid_volume", "ask_volume"])

                        for ms, bid, ask, bv, av in rows:
                            ts = datetime.fromtimestamp(base + ms / 1000,
                                                        tz=timezone.utc).isoformat()
                            b = bid / scale
                            a = ask / scale
                            bv2 = bv / 1000000
                            av2 = av / 1000000
                            if side == "Bid":
                                w.writerow([ts, b, bv2])
                            elif side == "Ask":
                                w.writerow([ts, a, av2])
                            else:
                                w.writerow([ts, b, a, bv2, av2])

                    self.write(f"OK    {day} {hour:02d}:00  ticks={len(rows):,}")

                except urllib.error.HTTPError as ex:
                    self.write(f"MISS  {day} {hour:02d}:00  HTTP {ex.code}")
                    failed.append((day, hour))
                except Exception as ex:
                    self.write(f"FAIL  {day} {hour:02d}:00  {ex}")
                    failed.append((day, hour))

            done_days += 1
            self.q.put(("progress", done_days / total_days * 100,
                        done_days, total_days, len(failed)))
            day = date.fromordinal(day.toordinal() + 1)

        self.q.put(("done", len(failed), str(out), self.stop_flag))

    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "log":
                    self.log.insert("end", item[1] + "\n")
                    self.log.see("end")
                elif item[0] == "progress":
                    _, p, done, total, failed = item
                    self.progress["value"] = p
                    self.status.config(text=f"Days: {done}/{total} | Failed chunks: {failed}")
                elif item[0] == "done":
                    _, failed, out, stopped = item
                    self.go.config(state="normal")
                    self.stop.config(state="disabled")
                    if stopped:
                        self.status.config(text="Stopped.")
                    else:
                        self.status.config(text=f"Finished. Failed chunks: {failed}")
                        messagebox.showinfo(
                            "Download complete",
                            f"Finished.\nFailed chunks: {failed}\nOutput: {out}"
                        )
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
