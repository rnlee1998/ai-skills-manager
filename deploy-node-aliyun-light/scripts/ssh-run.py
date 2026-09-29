#!/usr/bin/env python3
"""SSH 辅助脚本：远程执行命令 / 上传文件（支持密码或私钥）

用法:
  ssh-run.py exec "命令"             # 执行远程命令（root）
  ssh-run.py put 本地路径 远程路径    # 上传单个文件
  ssh-run.py putdir 本地目录 远程目录 # 上传整个目录（含子目录）

环境变量:
  SSH_HOST  默认 47.79.20.187
  SSH_USER  默认 root
  SSH_PASS  密码（有则优先用密码）
  SSH_KEY   私钥路径（如 C:/Users/Administrator/Desktop/workbuddy2.pem）
            SSH_PASS 为空时使用；未设置则尝试常见的几把本机 pem

私钥需为 OpenSSH/PEM 格式；PuTTY 的 .ppk 请先转换。
"""
import os, sys, posixpath
import paramiko

HOST = os.environ.get("SSH_HOST", "47.79.20.187")
PASS = os.environ.get("SSH_PASS", "")
USER = os.environ.get("SSH_USER", "root")

CANDIDATE_KEYS = [
    os.environ.get("SSH_KEY", ""),
    r"C:/Users/Administrator/Desktop/workbuddy2.pem",
    r"C:/Users/Administrator/Downloads/workbuddy2.pem",
    r"C:/Users/Administrator/Downloads/workbuddy.pem",
    r"C:/Users/Administrator/.ssh/id_rsa",
]


def pick_key():
    """返回第一个可用的私钥对象；找不到返回 None"""
    for p in CANDIDATE_KEYS:
        if not p or not os.path.isfile(p):
            continue
        loaders = [getattr(paramiko, n) for n in
                   ("RSAKey", "Ed25519Key", "ECDSAKey", "DSSKey")
                   if hasattr(paramiko, n)]
        for loader in loaders:
            try:
                k = loader.from_private_key_file(p)
                print(f"[auth] key: {p} ({type(k).__name__})", file=sys.stderr)
                return k
            except Exception:
                continue
        print(f"[warn] 无法解析私钥: {p}", file=sys.stderr)
    return None


def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = dict(port=22, username=USER, timeout=20,
              banner_timeout=20, auth_timeout=20,
              allow_agent=False, look_for_keys=False)
    if PASS:
        print(f"[auth] password auth as {USER}@{HOST}", file=sys.stderr)
        kw["password"] = PASS
    else:
        key = pick_key()
        if key is None:
            sys.exit("错误：未找到可用私钥，请设置 SSH_KEY 或 SSH_PASS")
        kw["pkey"] = key
    c.connect(HOST, **kw)
    return c


def run(cmd):
    c = connect()
    try:
        stdin, stdout, stderr = c.exec_command(cmd, timeout=120, get_pty=False)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        if out.strip():
            print(out.rstrip())
        if err.strip():
            print("[stderr] " + err.rstrip(), file=sys.stderr)
        return code
    finally:
        c.close()


def put(local, remote):
    c = connect()
    sftp = c.open_sftp()
    try:
        sftp.put(local, remote)
        print(f"uploaded: {local} -> {remote}")
    finally:
        sftp.close()
        c.close()


def putdir(local_dir, remote_dir):
    c = connect()
    sftp = c.open_sftp()
    try:
        def ensure_dir(p):
            try:
                sftp.stat(p)
            except IOError:
                sftp.mkdir(p)

        def walk_upload(l, r):
            ensure_dir(r)
            for name in sorted(os.listdir(l)):
                lp = os.path.join(l, name)
                rp = posixpath.join(r, name)
                if os.path.isdir(lp):
                    walk_upload(lp, rp)
                else:
                    sftp.put(lp, rp)
                    print(f"  {rp}")
        walk_upload(local_dir, remote_dir)
    finally:
        sftp.close()
        c.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    mode = sys.argv[1]
    if mode == "exec":
        sys.exit(run(sys.argv[2]))
    elif mode == "put":
        put(sys.argv[2], sys.argv[3])
    elif mode == "putdir":
        putdir(sys.argv[2], sys.argv[3])
    else:
        print("unknown mode", mode)
        sys.exit(2)
