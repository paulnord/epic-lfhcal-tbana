#!/usr/bin/env python3
"""ROOT-native provenance wrapper for LFHCal C/C++ analysis stages."""

from __future__ import annotations

import argparse
from array import array
import datetime as dt
import hashlib
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import socket
import subprocess
import sys
import warnings

SCHEMA_VERSION = 1
ENV_KEYS = [
    "PATH", "LD_LIBRARY_PATH", "ROOTSYS", "ROOT_INCLUDE_PATH",
    "ROOT_LIBRARY_PATH", "PYTHONPATH", "SINGULARITY_CONTAINER",
    "SINGULARITY_NAME", "APPTAINER_CONTAINER", "APPTAINER_NAME",
    "_CONDOR_SCRATCH_DIR",
]

STAGE_STR = [
    "record_id", "stage", "record_mode", "status", "started_utc",
    "finished_utc", "recorded_utc", "program", "command", "cwd",
    "git_commit", "git_branch", "git_diff", "decoder_commit",
    "decoder_diff", "hostname", "user", "os_pretty", "kernel",
    "architecture", "container_image", "container_runtime", "root_version",
    "compiler", "cmake_version", "executable_path", "executable_sha256",
    "condor_machine", "notes",
]
STAGE_INT = [
    "schema_version", "step", "run", "pedestal_run", "muon_run",
    "condor_cluster_id", "condor_proc_id", "condor_request_memory_mb",
]
STAGE_BOOL = ["git_dirty", "decoder_dirty"]

FILE_STR = [
    "record_id", "role", "label", "path", "mtime_utc", "root_uuid",
    "sha256", "note",
]
FILE_INT = ["step"]
FILE_LONG = ["size_bytes"]
FILE_BOOL = ["exists"]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def capture(argv, cwd=None, timeout=30):
    try:
        p = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return p.returncode, p.stdout.rstrip()
    except Exception as exc:
        return None, f"<capture failed: {exc!r}>"


def text(argv, cwd=None, timeout=30):
    return capture(argv, cwd=cwd, timeout=timeout)[1]


def first(s):
    return s.splitlines()[0].strip() if s else ""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def split_spec(spec, default):
    if "=" in spec:
        label, path = spec.split("=", 1)
        if label and path:
            return label, path
    return default, spec


def parse_attr(spec):
    if "=" not in spec:
        raise ValueError(f"attribute must be key=value: {spec}")
    return spec.split("=", 1)


def os_release():
    out = {}
    p = Path("/etc/os-release")
    if p.is_file():
        for line in p.read_text(errors="replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v.strip().strip('"')
    return out


def git_meta(path):
    rc, root = capture(["git", "-C", path, "rev-parse", "--show-toplevel"])
    if rc != 0:
        return {"root":"", "commit":"", "branch":"", "dirty":False,
                "diff":"", "remotes":""}
    root = root.strip()
    def git(*args): return capture(["git", "-C", root, *args])[1]
    status = git("status", "--porcelain=v1")
    dirty = bool(status.strip())
    diff = git("diff", "--no-ext-diff", "HEAD") if dirty else ""
    if len(diff.encode()) > 1000000:
        diff = diff.encode()[:1000000].decode(errors="replace") + "\n<TRUNCATED>"
    return {
        "root": root,
        "commit": git("rev-parse", "HEAD").strip(),
        "branch": git("symbolic-ref", "--short", "-q", "HEAD").strip(),
        "dirty": dirty,
        "diff": diff,
        "remotes": git("remote", "-v"),
    }


def condor_meta():
    out = {}
    p = os.environ.get("_CONDOR_JOB_AD")
    wanted = {"ClusterId", "ProcId", "RequestMemory", "Machine", "RemoteHost"}
    if p and Path(p).is_file():
        for line in Path(p).read_text(errors="replace").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                if k in wanted:
                    out[k] = v.strip().strip('"')
    return out


def executable_path(argv0, cwd):
    if not argv0:
        return None
    if "/" in argv0:
        p = Path(argv0)
        if not p.is_absolute(): p = Path(cwd) / p
        return p.resolve() if p.exists() else None
    found = shutil.which(argv0)
    return Path(found).resolve() if found else None


def parse_ldd(s):
    rows = []
    for line in s.splitlines():
        line = line.strip()
        if not line: continue
        m = re.match(r"^(\S+)\s+=>\s+(\S+)(?:\s+\(.*\))?$", line)
        if m:
            rows.append({"name":m.group(1), "path":m.group(2)})
        else:
            m = re.match(r"^(\S+)\s+\(.*\)$", line)
            rows.append({"name":m.group(1) if m else line, "path":""})
    return rows


def root_meta(ROOT, path):
    p = Path(path)
    row = {"path":str(p), "exists":p.exists(), "size_bytes":-1,
           "mtime_utc":"", "root_uuid":"", "sha256":"", "note":""}
    if not p.exists(): return row
    st = p.stat()
    row["size_bytes"] = st.st_size
    row["mtime_utc"] = dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat()
    f = ROOT.TFile.Open(str(p), "READ")
    if f and not f.IsZombie():
        try: row["root_uuid"] = str(f.GetUUID().AsString())
        except Exception: pass
        f.Close()
    else:
        row["note"] = "not a valid ROOT file"
    return row


def config_meta(path):
    p = Path(path)
    row = {"path":str(p), "exists":p.exists(), "size_bytes":-1,
           "mtime_utc":"", "root_uuid":"", "sha256":"", "note":""}
    if p.exists():
        st = p.stat()
        row["size_bytes"] = st.st_size
        row["mtime_utc"] = dt.datetime.fromtimestamp(st.st_mtime, dt.timezone.utc).isoformat()
        if p.is_file(): row["sha256"] = sha256(p)
    return row


class Writer:
    def __init__(self, ROOT, name, title, sfields, ifields=(), lfields=(), bfields=()):
        self.tree = ROOT.TTree(name, title)
        self.s, self.i, self.l, self.b = {}, {}, {}, {}
        for n in sfields:
            x = ROOT.std.string(); self.s[n] = x; self.tree.Branch(n, x)
        for n in ifields:
            x = array("i", [0]); self.i[n] = x; self.tree.Branch(n, x, f"{n}/I")
        for n in lfields:
            x = array("q", [0]); self.l[n] = x; self.tree.Branch(n, x, f"{n}/L")
        for n in bfields:
            x = array("b", [0]); self.b[n] = x; self.tree.Branch(n, x, f"{n}/O")
    def fill(self, row):
        for n,x in self.s.items(): x.assign(str(row.get(n,"")))
        for n,x in self.i.items(): x[0] = int(row.get(n,-1))
        for n,x in self.l.items(): x[0] = int(row.get(n,-1))
        for n,x in self.b.items(): x[0] = 1 if row.get(n,False) else 0
        self.tree.Fill()


def read_rows(tree, sfields, ifields=(), lfields=(), bfields=()):
    if not tree: return []
    names = {str(b.GetName()) for b in tree.GetListOfBranches()}
    out = []
    for e in tree:
        r = {}
        for n in sfields: r[n] = str(getattr(e,n)) if n in names else ""
        for n in ifields: r[n] = int(getattr(e,n)) if n in names else -1
        for n in lfields: r[n] = int(getattr(e,n)) if n in names else -1
        for n in bfields: r[n] = bool(getattr(e,n)) if n in names else False
        out.append(r)
    return out


def read_history(ROOT, path):
    empty = {"stages":[], "files":[], "libraries":[], "environment":[], "attributes":[]}
    if not Path(path).is_file(): return empty
    f = ROOT.TFile.Open(path, "READ")
    if not f or f.IsZombie(): return empty
    h = {
        "stages": read_rows(f.Get("Provenance"), STAGE_STR, STAGE_INT, (), STAGE_BOOL),
        "files": read_rows(f.Get("ProvenanceFiles"), FILE_STR, FILE_INT, FILE_LONG, FILE_BOOL),
        "libraries": read_rows(f.Get("ProvenanceLibraries"), ["record_id","name","path"], ["step"]),
        "environment": read_rows(f.Get("ProvenanceEnvironment"), ["record_id","key","value"], ["step"]),
        "attributes": read_rows(f.Get("ProvenanceAttributes"), ["record_id","key","value"], ["step"]),
    }
    f.Close(); return h


def merge(histories):
    order, stages = [], {}
    aux = {k:{} for k in ["files","libraries","environment","attributes"]}
    for h in histories:
        for s in h["stages"]:
            rid = s.get("record_id","")
            if rid and rid not in stages:
                order.append(rid); stages[rid] = dict(s)
        for k in aux:
            for r in h[k]:
                rid = r.get("record_id","")
                if rid: aux[k].setdefault(rid, []).append(dict(r))
    out = {"stages":[], "files":[], "libraries":[], "environment":[], "attributes":[]}
    seen = {k:set() for k in aux}
    for step,rid in enumerate(order):
        s = dict(stages[rid]); s["step"] = step; out["stages"].append(s)
        for k in aux:
            for r in aux[k].get(rid,[]):
                r = dict(r); r["step"] = step
                sig = tuple(sorted((a,repr(b)) for a,b in r.items() if a != "step"))
                if sig in seen[k]: continue
                seen[k].add(sig); out[k].append(r)
    return out


def write_history(ROOT, path, h):
    f = ROOT.TFile.Open(path, "UPDATE")
    if not f or f.IsZombie(): raise RuntimeError(f"cannot update {path}")
    for name in ["Provenance","ProvenanceFiles","ProvenanceLibraries",
                 "ProvenanceEnvironment","ProvenanceAttributes","ProvenanceREADME"]:
        f.Delete(f"{name};*")
    w = Writer(ROOT,"Provenance","one row per processing stage",STAGE_STR,STAGE_INT,(),STAGE_BOOL)
    for r in h["stages"]: w.fill(r)
    w.tree.Write("Provenance", ROOT.TObject.kOverwrite)
    w = Writer(ROOT,"ProvenanceFiles","files used by each stage",FILE_STR,FILE_INT,FILE_LONG,FILE_BOOL)
    for r in h["files"]: w.fill(r)
    w.tree.Write("ProvenanceFiles", ROOT.TObject.kOverwrite)
    w = Writer(ROOT,"ProvenanceLibraries","linked libraries",["record_id","name","path"],["step"])
    for r in h["libraries"]: w.fill(r)
    w.tree.Write("ProvenanceLibraries", ROOT.TObject.kOverwrite)
    w = Writer(ROOT,"ProvenanceEnvironment","selected environment",["record_id","key","value"],["step"])
    for r in h["environment"]: w.fill(r)
    w.tree.Write("ProvenanceEnvironment", ROOT.TObject.kOverwrite)
    w = Writer(ROOT,"ProvenanceAttributes","extra key/value attributes",["record_id","key","value"],["step"])
    for r in h["attributes"]: w.fill(r)
    w.tree.Write("ProvenanceAttributes", ROOT.TObject.kOverwrite)
    ROOT.TNamed("ProvenanceREADME",
        "ROOT-native LFHCal provenance. Trees are joined by record_id and step. No JSON payload is used.").Write(
        "ProvenanceREADME", ROOT.TObject.kOverwrite)
    f.Write("", ROOT.TObject.kOverwrite); f.Close()


def validate(ROOT, path):
    p = Path(path)
    if not p.is_file() or p.stat().st_size <= 0: raise RuntimeError(f"missing/empty output: {path}")
    f = ROOT.TFile.Open(path,"READ"); ok = bool(f) and not f.IsZombie()
    if f: f.Close()
    if not ok: raise RuntimeError(f"invalid ROOT file: {path}")


def stage_base(args, mode):
    return {
        "schema_version":SCHEMA_VERSION, "step":-1, "record_id":"",
        "stage":args.stage, "record_mode":mode, "status":"success",
        "started_utc":"", "finished_utc":"", "recorded_utc":now(),
        "program":"", "command":"", "cwd":getattr(args,"cwd",os.getcwd()),
        "run":getattr(args,"run",-1), "pedestal_run":getattr(args,"pedestal_run",-1),
        "muon_run":getattr(args,"muon_run",-1), "git_commit":"", "git_branch":"",
        "git_dirty":False, "git_diff":"", "decoder_commit":"", "decoder_dirty":False,
        "decoder_diff":"", "hostname":"", "user":"", "os_pretty":"", "kernel":"",
        "architecture":"", "container_image":"", "container_runtime":"", "root_version":"",
        "compiler":"", "cmake_version":"", "executable_path":"", "executable_sha256":"",
        "condor_cluster_id":-1, "condor_proc_id":-1, "condor_request_memory_mb":-1,
        "condor_machine":"", "notes":"\n".join(getattr(args,"note",[]) or []),
    }


def runtime(ROOT, command, cwd):
    g = git_meta(cwd)
    dg = git_meta(str(Path(g["root"])/"NewStructure"/"h2g_decode")) if g["root"] else git_meta(".")
    exe = executable_path(command[0] if command else "", cwd)
    ldd = text(["ldd",str(exe)]) if exe else ""
    libs = parse_ldd(ldd)
    osr = os_release(); u = platform.uname(); cond = condor_meta()
    image = os.environ.get("APPTAINER_CONTAINER") or os.environ.get("SINGULARITY_CONTAINER") or ""
    crt = first(text(["apptainer","--version"]))
    if crt.startswith("<capture failed"): crt = first(text(["singularity","--version"]))
    clang = first(text(["clang++","--version"])); gcc = first(text(["g++","--version"]))
    fields = {
        "git_commit":g["commit"], "git_branch":g["branch"], "git_dirty":g["dirty"], "git_diff":g["diff"],
        "decoder_commit":dg["commit"], "decoder_dirty":dg["dirty"], "decoder_diff":dg["diff"],
        "hostname":socket.getfqdn(), "user":os.environ.get("USER",""),
        "os_pretty":osr.get("PRETTY_NAME",platform.platform()), "kernel":f"{u.system} {u.release}",
        "architecture":u.machine, "container_image":image, "container_runtime":crt,
        "root_version":str(ROOT.gROOT.GetVersion()),
        "compiler":clang if not clang.startswith("<capture failed") else gcc,
        "cmake_version":first(text(["cmake","--version"])),
        "executable_path":str(exe) if exe else "", "executable_sha256":sha256(exe) if exe and exe.is_file() else "",
        "condor_cluster_id":int(cond.get("ClusterId",-1)), "condor_proc_id":int(cond.get("ProcId",-1)),
        "condor_request_memory_mb":int(cond.get("RequestMemory",-1)),
        "condor_machine":cond.get("Machine",cond.get("RemoteHost","")),
    }
    env = [{"key":k,"value":os.environ[k]} for k in ENV_KEYS if k in os.environ]
    attrs = [
        {"key":"analysis_git_root","value":g["root"]}, {"key":"analysis_git_remotes","value":g["remotes"]},
        {"key":"decoder_git_root","value":dg["root"]}, {"key":"decoder_git_remotes","value":dg["remotes"]},
        {"key":"root_config_version","value":text(["root-config","--version"])},
        {"key":"root_config_arch","value":text(["root-config","--arch"])},
        {"key":"root_config_cflags","value":text(["root-config","--cflags"])},
        {"key":"root_config_libs","value":text(["root-config","--libs"])},
    ]
    return fields, libs, env, attrs


def file_rows(ROOT, inputs, outputs, configs):
    rows=[]
    for spec in inputs:
        label,path=split_spec(spec,"input"); r=root_meta(ROOT,path); r.update(role="input",label=label); rows.append(r)
    for spec in outputs:
        label,path=split_spec(spec,"output"); r=root_meta(ROOT,path); r.update(role="output",label=label,note="metadata before provenance write"); rows.append(r)
    for spec in configs:
        label,path=split_spec(spec,"config"); r=config_meta(path); r.update(role="config",label=label); rows.append(r)
    return rows


def record_id(stage, files):
    parts=[f"S:{k}={stage[k]!r}" for k in sorted(stage) if k != "record_id"]
    for r in sorted(files,key=lambda x:(x.get("role",""),x.get("label",""),x.get("path",""))):
        parts.append("F:"+"|".join(f"{k}={r[k]!r}" for k in sorted(r) if k not in {"record_id","step"}))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def append(h, stage, files, libs, env, attrs):
    step=len(h["stages"]); stage=dict(stage); stage["step"]=step; rid=stage["record_id"]; h["stages"].append(stage)
    for kind,rows in [("files",files),("libraries",libs),("environment",env),("attributes",attrs)]:
        for row in rows:
            r=dict(row); r["record_id"]=rid; r["step"]=step; h[kind].append(r)
    return h


def cmd_run(ROOT,args):
    command=list(args.command); command=command[1:] if command and command[0]=="--" else command
    if not command: raise RuntimeError("missing analysis command after --")
    inpaths=[split_spec(x,"input")[1] for x in args.input]
    outpaths=[split_spec(x,"output")[1] for x in args.output]
    for p in inpaths:
        if not Path(p).exists(): raise RuntimeError(f"missing input: {p}")
    started=now(); print(f"Stage: {args.stage}\nCommand: {shlex.join(command)}",flush=True)
    rc=subprocess.run(command,cwd=args.cwd,check=False).returncode; finished=now()
    if rc: raise RuntimeError(f"stage failed with exit code {rc}; no success provenance written")
    for p in outpaths: validate(ROOT,p)
    h=merge([read_history(ROOT,p) for p in inpaths])
    s=stage_base(args,"executed"); s.update(started_utc=started,finished_utc=finished,program=command[0],command=shlex.join(command))
    fields,libs,env,attrs=runtime(ROOT,command,args.cwd); s.update(fields)
    attrs += [dict(zip(("key","value"),parse_attr(x))) for x in args.attribute]
    files=file_rows(ROOT,args.input,args.output,args.config); s["record_id"]=record_id(s,files)
    h=append(h,s,files,libs,env,attrs)
    for p in outpaths: write_history(ROOT,p,h)
    print(f"Completed {args.stage}; provenance stages={len(h['stages'])}")
    return 0


def cmd_stamp(ROOT,args):
    validate(ROOT,args.root_file)
    h=merge([read_history(ROOT,p) for p in args.parent]+[read_history(ROOT,args.root_file)])
    s=stage_base(args,"retrospective"); s["program"]=args.program or ""; s["command"]=args.command_text or ""; s["started_utc"]=args.started_utc or ""; s["finished_utc"]=args.finished_utc or ""
    for k in ["git_commit","decoder_commit","container_image","root_version","compiler","hostname","os_pretty"]:
        v=getattr(args,k,None)
        if v: s[k]=v
    attrs=[{"key":"retrospective_warning","value":"record added after file creation; only supplied historical fields describe original processing"}]
    attrs += [dict(zip(("key","value"),parse_attr(x))) for x in args.attribute]
    files=file_rows(ROOT,args.parent,[f"retrospectively_stamped={args.root_file}"],args.config); s["record_id"]=record_id(s,files)
    h=append(h,s,files,[],[],attrs); write_history(ROOT,args.root_file,h)
    print(f"Stamped {args.root_file}; provenance stages={len(h['stages'])}")
    return 0


def cmd_show(ROOT,args):
    h=read_history(ROOT,args.root_file)
    if not h["stages"]: print("No Provenance tree found."); return 1
    print(f"{'step':>4}  {'stage':<24} {'mode':<13} {'run':>6} {'ped':>6} {'muon':>6}  {'git':<10} {'ROOT':<10}")
    for r in h["stages"]:
        print(f"{r['step']:>4}  {r['stage'][:24]:<24} {r['record_mode'][:13]:<13} {r['run']:>6} {r['pedestal_run']:>6} {r['muon_run']:>6}  {r['git_commit'][:10]:<10} {r['root_version'][:10]:<10}")
    return 0


def cmd_verify(ROOT,args):
    validate(ROOT,args.root_file); h=read_history(ROOT,args.root_file)
    print(f"ROOT file: {args.root_file}\nProvenance stages: {len(h['stages'])}\nFile rows: {len(h['files'])}\nLibrary rows: {len(h['libraries'])}\nEnvironment rows: {len(h['environment'])}\nAttribute rows: {len(h['attributes'])}")
    if [r['step'] for r in h['stages']] != list(range(len(h['stages']))): raise RuntimeError("non-contiguous provenance steps")
    print("Verification: OK"); return 0


def cmd_schema():
    print("TTree Provenance: one row per stage\nTTree ProvenanceFiles: input/output/config rows\nTTree ProvenanceLibraries: ldd rows\nTTree ProvenanceEnvironment: selected environment\nTTree ProvenanceAttributes: arbitrary key/value annotations")
    return 0


def parser():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    r=sub.add_parser("run"); r.add_argument("--stage",required=True); r.add_argument("--input",action="append",default=[]); r.add_argument("--output",action="append",required=True); r.add_argument("--config",action="append",default=[]); r.add_argument("--run",type=int,default=-1); r.add_argument("--pedestal-run",type=int,default=-1); r.add_argument("--muon-run",type=int,default=-1); r.add_argument("--note",action="append",default=[]); r.add_argument("--attribute",action="append",default=[]); r.add_argument("--cwd",default=os.getcwd()); r.add_argument("command",nargs=argparse.REMAINDER)
    s=sub.add_parser("stamp-existing"); s.add_argument("root_file"); s.add_argument("--stage",required=True); s.add_argument("--parent",action="append",default=[]); s.add_argument("--config",action="append",default=[]); s.add_argument("--run",type=int,default=-1); s.add_argument("--pedestal-run",type=int,default=-1); s.add_argument("--muon-run",type=int,default=-1); s.add_argument("--program"); s.add_argument("--command-text"); s.add_argument("--started-utc"); s.add_argument("--finished-utc"); s.add_argument("--git-commit"); s.add_argument("--decoder-commit"); s.add_argument("--container-image"); s.add_argument("--root-version"); s.add_argument("--compiler"); s.add_argument("--hostname"); s.add_argument("--os-pretty"); s.add_argument("--note",action="append",default=[]); s.add_argument("--attribute",action="append",default=[]); s.add_argument("--cwd",default=os.getcwd())
    sh=sub.add_parser("show"); sh.add_argument("root_file")
    v=sub.add_parser("verify"); v.add_argument("root_file")
    sub.add_parser("schema"); return p


def main():
    args=parser().parse_args()
    try: import ROOT
    except Exception as exc:
        print(f"ERROR: PyROOT required; run in EIC analysis environment: {exc}",file=sys.stderr); return 2
    ROOT.gROOT.SetBatch(True)

    # LFHCal files contain custom C++ classes.  The provenance process does
    # not need those objects, but ROOT otherwise emits a large amount of
    # dictionary/autoload chatter merely while opening the file.
    ROOT.gErrorIgnoreLevel = ROOT.kError
    warnings.filterwarnings(
        "ignore",
        message=r".*no dictionary for class.*",
        category=RuntimeWarning,
    )
    try:
        if args.cmd=="run": return cmd_run(ROOT,args)
        if args.cmd=="stamp-existing": return cmd_stamp(ROOT,args)
        if args.cmd=="show": return cmd_show(ROOT,args)
        if args.cmd=="verify": return cmd_verify(ROOT,args)
        if args.cmd=="schema": return cmd_schema()
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr); return 1
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
