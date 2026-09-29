#!/usr/bin/env python3
"""Pure-Python Windows minidump triage. No WinDbg / no dependencies.

Extracts: exception stream, loaded module list, crashing thread context and a
stack scan (which modules have code/pointers on the crashing thread's stack).

Usage:
    python minidump_triage.py <path-to.dmp> [-o out.txt]

Report is written as UTF-8 to <dump>.triage.txt by default so that Windows
console code-page issues never garble the output.
"""

import argparse
import datetime
import io
import os
import struct
import sys
from collections import Counter

# --- minidump stream types ---
ST_THREAD_LIST = 3
ST_MODULE_LIST = 4
ST_MEMORY_LIST = 5
ST_EXCEPTION = 6
ST_SYSTEM_INFO = 7
ST_MEMORY_INFO_LIST = 15
ST_THREAD_INFO_LIST = 17

EXCEPTION_NAMES = {
    0xC0000005: "EXCEPTION_ACCESS_VIOLATION",
    0xC00000FD: "EXCEPTION_STACK_OVERFLOW",
    0xC000001D: "EXCEPTION_ILLEGAL_INSTRUCTION",
    0xC0000025: "EXCEPTION_NONCONTINUABLE_EXCEPTION",
    0xC000008C: "EXCEPTION_ARRAY_BOUNDS_EXCEEDED",
    0xC0000094: "EXCEPTION_INT_DIVIDE_BY_ZERO",
    0xC0000095: "EXCEPTION_INT_OVERFLOW",
    0xC0000096: "EXCEPTION_PRIV_INSTRUCTION",
    0xC00000F4: "EXCEPTION_ILLEGAL_FLOAT_CONTEXT",
    0xC0000374: "EXCEPTION_HEAP_CORRUPTION",
    0xC0000409: "EXCEPTION_STACK_BUFFER_OVERRUN (__fastfail)",
    0xC0000602: "FAIL_FAST_EXCEPTION",
    0x80000003: "EXCEPTION_BREAKPOINT (assert)",
    0x80000004: "EXCEPTION_SINGLE_STEP",
    0xE06D7363: "C++ exception",
}

ACCESS_OP = {0: "READ", 1: "WRITE", 8: "EXECUTE", 16: "DEP"}


def _u16(b):
    return b.decode("utf-16-le", errors="replace")


class MiniDump:
    def __init__(self, path):
        self.path = path
        with io.open(path, "rb") as f:
            self.data = f.read()
        self.streams = []
        self.modules = []
        self.exception = None
        self.threads = []
        self._parse_header()
        self._parse_streams()

    # ---------- header / streams ----------
    def _parse_header(self):
        d = self.data
        if len(d) < 32:
            raise ValueError("file too small to be a minidump")
        if d[0:4] != b"MDMP":
            raise ValueError("bad signature %r (expected b'MDMP')" % d[0:4])
        version, nstreams, dir_rva, checksum, ts, f_lo, f_hi = struct.unpack_from(
            "<IIIIIII", d, 4
        )
        self.version = version
        self.timestamp = ts
        self.flags = (f_hi << 32) | f_lo
        for i in range(nstreams):
            st, ds, rva = struct.unpack_from("<III", d, dir_rva + i * 12)
            self.streams.append((st, ds, rva))

    def _md_string(self, rva):
        if not rva:
            return ""
        ln = struct.unpack_from("<I", self.data, rva)[0]
        return _u16(self.data[rva + 4 : rva + 4 + ln])

    def _parse_streams(self):
        d = self.data
        for st, ds, rva in self.streams:
            if st == ST_MODULE_LIST:
                nmod = struct.unpack_from("<I", d, rva)[0]
                off = rva + 4
                for _ in range(nmod):
                    base, size, csum, mts, namerva = struct.unpack_from(
                        "<QIIII", d, off
                    )
                    self.modules.append((base, size, self._md_string(namerva)))
                    off += 108  # sizeof(MINIDUMP_MODULE)
            elif st == ST_THREAD_LIST:
                n = struct.unpack_from("<I", d, rva)[0]
                off = rva + 4
                for _ in range(n):
                    vals = struct.unpack_from("<IIIIQQIIII", d, off)
                    tid, sstart, ssize, srva, csz, crva = (
                        vals[0],
                        vals[5],
                        vals[6],
                        vals[7],
                        vals[8],
                        vals[9],
                    )
                    self.threads.append(
                        {
                            "tid": tid,
                            "stack_start": sstart,
                            "stack_size": ssize,
                            "stack_rva": srva,
                            "ctx_rva": crva,
                        }
                    )
                    off += 48  # sizeof(MINIDUMP_THREAD)
            elif st == ST_EXCEPTION:
                tid = struct.unpack_from("<I", d, rva)[0]
                er = rva + 8
                code, flags, rec, eaddr, nparams, _al = struct.unpack_from(
                    "<IIQQII", d, er
                )
                params = struct.unpack_from("<15Q", d, er + 32)
                self.exception = {
                    "thread_id": tid,
                    "code": code,
                    "flags": flags,
                    "record": rec,
                    "address": eaddr,
                    "nparams": nparams,
                    "params": params,
                }

    # ---------- helpers ----------
    def module_of(self, addr):
        for base, size, name in self.modules:
            if base <= addr < base + size:
                return name, addr - base
        return None, None

    def short(self, name):
        return name.replace("/", "\\").split("\\")[-1]

    # ---------- report ----------
    def render(self):
        out = []
        a = out.append
        a("=== minidump triage ===")
        a("file          : %s" % self.path)
        a("size          : %d bytes" % len(self.data))
        a("mdmp version  : 0x%08X" % self.version)
        try:
            dt = datetime.datetime.fromtimestamp(self.timestamp, datetime.timezone.utc)
            a("dump time     : %s (UTC)" % dt.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            a("dump time     : (unparsable timestamp %d)" % self.timestamp)
        a("streams       : %d" % len(self.streams))
        a("modules       : %d" % len(self.modules))
        a("threads       : %d" % len(self.threads))

        # exception
        a("")
        a("=== exception ===")
        ex = self.exception
        if not ex:
            a("no exception stream present (dump may be a client-side/abort dump)")
        else:
            code = ex["code"]
            a("thread id     : %d (0x%X)" % (ex["thread_id"], ex["thread_id"]))
            a(
                "exception code: 0x%08X  %s"
                % (code, EXCEPTION_NAMES.get(code, "(unknown / nonstandard)"))
            )
            a("flags         : 0x%08X" % ex["flags"])
            a("address       : 0x%016X" % ex["address"])
            mn, off = self.module_of(ex["address"])
            if mn:
                a("  -> in module : %s + 0x%X" % (self.short(mn), off))
            else:
                a("  -> not inside any loaded module (wild or freed pointer)")
            a("param count   : %d" % ex["nparams"])
            for i in range(min(ex["nparams"], 15)):
                a("  param[%d]    : 0x%016X" % (i, ex["params"][i]))
            if code == 0xC0000005 and ex["nparams"] >= 2:
                op = ACCESS_OP.get(ex["params"][0], str(ex["params"][0]))
                bad = ex["params"][1]
                a("  -> ACCESS VIOLATION on %s at 0x%016X" % (op, bad))
                mn2, off2 = self.module_of(bad)
                if mn2:
                    a("  -> bad address in module: %s + 0x%X" % (self.short(mn2), off2))
                else:
                    a("  -> bad address NOT in any module (use-after-free / wild ptr)")

        # thread context + stack scan
        a("")
        a("=== crashing thread stack ===")
        tgt = None
        if ex:
            for t in self.threads:
                if t["tid"] == ex["thread_id"]:
                    tgt = t
                    break
        if tgt is None:
            a("crashing thread not found in thread list; skipping stack scan")
        else:
            ctx = tgt["ctx_rva"]
            if ctx:
                # CONTEXT_X64: Rsp @0x98, Rbp @0xA0, Rip @0xF8
                rip = struct.unpack_from("<Q", self.data, ctx + 0xF8)[0]
                rsp = struct.unpack_from("<Q", self.data, ctx + 0x98)[0]
                rbp = struct.unpack_from("<Q", self.data, ctx + 0xA0)[0]
                a("RIP           : 0x%016X" % rip)
                mn, off = self.module_of(rip)
                if mn:
                    a("  -> in module : %s + 0x%X" % (self.short(mn), off))
                a("RSP           : 0x%016X" % rsp)
                a("RBP           : 0x%016X" % rbp)
            stack = self.data[
                tgt["stack_rva"] : tgt["stack_rva"] + tgt["stack_size"]
            ]
            a("stack bytes   : %d" % len(stack))
            hits = []
            for i in range(0, max(0, len(stack) - 8), 8):
                v = struct.unpack_from("<Q", stack, i)[0]
                if not v:
                    continue
                for base, size, name in self.modules:
                    if base <= v < base + size:
                        hits.append((tgt["stack_start"] + i, v, name, v - base))
                        break
            a("")
            a("-- stack words pointing into loaded modules (first 120) --")
            for addr, v, name, off in hits[:120]:
                a("  0x%016X -> %s + 0x%X" % (addr, self.short(name), off))
            a("")
            a("-- module frequency on stack (top 30) --")
            for name, n in Counter(self.short(h[2]) for h in hits).most_common(30):
                a("  %-52s %d" % (name, n))

        # module list
        a("")
        a("=== loaded modules (%d) ===" % len(self.modules))
        for base, size, name in self.modules:
            a("  0x%016X  size=0x%08X  %s" % (base, size, name))

        return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Pure-Python minidump triage")
    ap.add_argument("dump", help="path to .dmp file")
    ap.add_argument("-o", "--out", help="output report path")
    args = ap.parse_args()

    if not os.path.isfile(args.dump):
        sys.stderr.write("no such file: %s\n" % args.dump)
        return 2

    try:
        md = MiniDump(args.dump)
    except Exception as e:
        sys.stderr.write("failed to parse: %s\n" % e)
        return 1

    report = md.render()
    out_path = args.out or (args.dump + ".triage.txt")
    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    sys.stdout.write("report written: %s\n" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
