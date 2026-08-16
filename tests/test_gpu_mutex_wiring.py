"""GPU_MUTEX must actually be ACQUIRED by the tools that touch CUDA.

`ops/loop/winmutex.py` has declared GPU_MUTEX since it was written, and its
docstring says it is "acquired by the TOOL that touches CUDA rather than by the
loop, so a manual run is protected too". Measured 2026-08-01: nothing acquired
it. The only hold() call in the repo was GEMINI_MUTEX in loop_controller, and
no file under tools/ imported winmutex at all. A declared-but-inert mutex reads
as protection in code review and provides none at runtime, which is worse than
no mutex: it is the reason a third headless loop joining the shared slot bucket
looked safe.

WHAT THIS FILE CAN AND CANNOT TEST. The suite runs under system python with no
GPU and none of the four tool venvs, so every assertion here is about WIRING -
that the acquisition exists at the right call site, that the CPU fallback does
not take it, that a venv which cannot see winmutex degrades instead of dying.
Nothing here proves two processes actually serialize; only a concurrent run
does that, and the ACQUIRED/RELEASED lines winmutex logs are what makes that
measurable afterwards.

THE SELF-DEADLOCK TRAP, which is why the acquisition sites are where they are.
A Windows named mutex is re-entrant per THREAD, not per process tree. A child
process that waits on a mutex its parent holds blocks forever. LW is layered
exactly that way - tools/lw_first_pass.py spawns .venv-upscale python for the
upscale and .venv-metrics python for the metrics - so acquisition lives at the
LEAF and never at an orchestrator. test_no_python_child_is_spawned_inside_a_hold
and test_known_orchestrators_do_not_acquire are the guards that keep it there.

TWO HYBRIDS, not one. lw_gen_run and lw_gen_weaponpass are each a CUDA worker
AND a spawner of a child that acquires, so each is split: the hold sits on the
in-process CUDA work and never spans the shell-out. The weapon pass is the
harder of the two because it reaches its child through a CLOSURE in a local
variable, which no lexical sweep can resolve - hence the named per-file guards
test_gen_run_does_not_hold_across_its_qa_subprocess and
test_weaponpass_does_not_hold_across_its_gate_subprocess alongside the generic
sweep. The sweep itself was widened 2026-08-01 to see os.system, from-imported
spawners, aliased modules, and a hold that calls a local helper which spawns one
frame down; test_the_spawn_guard_catches_the_shapes_it_claims_to_catch is its
self-test.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import lw_clean_iopaint as iopaint  # noqa: E402
import lw_clean_pass as cleanpass  # noqa: E402
import lw_clean_sdxl as sdxl  # noqa: E402
import lw_g1_gate as g1  # noqa: E402
import lw_gen_qa as genqa  # noqa: E402
import lw_gen_run as genrun  # noqa: E402
import lw_upscale as upscale  # noqa: E402

# The name every tool exposes for the acquisition helper. One name across four
# venvs is what makes the AST guards below possible at all.
LOCK_NAME = "gpu_lock"

# (module, filename, function-that-must-acquire). Function names, not line
# numbers: line numbers drift on every edit above them and a drifted guard
# either fails spuriously or, worse, silently stops pointing at the code it
# guards. Each entry is the LEAF that does the CUDA work - see the module
# docstring for why never the orchestrator.
ACQUIRE_SITES = [
    # spandrel model load + tiled inference + empty_cache. first_pass() calls
    # this; first_pass itself must NOT acquire (it also has a downscale-only
    # branch that never touches the GPU).
    ("lw_upscale.py", "upscale_spandrel"),
    # realesrgan-ncnn-vulkan.exe is a Vulkan GPU consumer even though no torch
    # is involved. It is a non-python exe that will never acquire, so spawning
    # it inside the hold cannot deadlock.
    ("lw_upscale.py", "upscale_ncnn"),
    # SDXL inpaint: the pipe is moved to cuda in build_inpaint_pipe and stays
    # resident for the whole worklist, so the hold spans load + every item.
    ("lw_clean_sdxl.py", "run_worklist"),
    ("lw_clean_sdxl.py", "selfcheck"),
    # YOLO + EasyOCR (detect) and SimpleLama (inpaint) are two separate GPU
    # phases of one slug, called in sequence by process_slug - not nested.
    ("lw_clean_pass.py", "detect_image"),
    ("lw_clean_pass.py", "_auto_inpaint"),
    ("lw_clean_iopaint.py", "clean_slug"),
    # pyiqa metric construction + evaluation, cuda only.
    ("lw_g1_gate.py", "fr_metrics"),
    # SDXL generation. Split across two holds on purpose - see
    # test_gen_run_does_not_hold_across_its_qa_subprocess.
    ("lw_gen_run.py", "_load_pipeline"),
    ("lw_gen_run.py", "_generate_candidates"),
    # open-clip QA scoring. score_batch takes ONE hold for the whole candidate
    # list (the model is already resident; releasing between candidates would
    # only hand another process a card LW still occupies) and weapon_crop_report
    # takes one for the single --weapon-crop encode. Both are pure leaves: this
    # module has no subprocess call at all, so no split is needed here.
    # medium yardstick: one hold covering the CLIP load plus every encode in
    # the set, mirroring ClipScorer.load + score_batch. No subprocess inside.
    ("lw_gen_medium.py", "encode_paths"),
    ("lw_gen_qa.py", "score_batch"),
    ("lw_gen_qa.py", "weapon_crop_report"),
    # Weapon pass. TWO sites, both strictly inside the in-process CUDA work -
    # see test_weaponpass_does_not_hold_across_its_gate_subprocess for why the
    # fix loop itself must stay unheld.
    ("lw_gen_weaponpass.py", "_build_real_inpainter"),
    ("lw_gen_weaponpass.py", "_inpaint"),
    # W4 LoRA training. Hand-run leaf with no spawn site anywhere in tools/ or
    # ops/, and no CPU path at all (train() refuses without CUDA).
    ("lw_gen_train_weapon_lora.py", "train"),
]

# (file, class, method) for acquisitions that live on a METHOD. _funcs() keys on
# the bare name and ClipScorer.load / WeaponClipScorer.load collide there, so a
# bare-name guard would silently check only one of the two.
ACQUIRE_METHODS = [
    ("lw_gen_qa.py", "ClipScorer", "load"),
    ("lw_gen_qa.py", "WeaponClipScorer", "load"),
]

# Tools that acquire but must NOT carry their own copy of the helper: each runs
# in a venv where an existing owner is already importable, so a fresh copy would
# be one more place for GPU_MUTEX_TIMEOUT_S to drift. lw_gen_qa runs in
# .venv-metrics alongside lw_g1_gate; the other two run in .venv-gen alongside
# lw_gen_run.
BORROWERS = {
    "lw_gen_qa.py": "lw_g1_gate",
    "lw_gen_weaponpass.py": "lw_gen_run",
    "lw_gen_train_weapon_lora.py": "lw_gen_run",
}

# Modules that carry their OWN copy of the helper. Four copies exist because
# these tools run under four different venvs (.venv-upscale, .venv-metrics,
# .venv-gen, C:\Tools\lw-clean\venv) and no single tools/ helper module is
# importable from all of them - lw_upscale in particular is contractually
# limited to PIL + numpy + stdlib at module top level.
LOCK_OWNERS = [upscale, sdxl, g1, genrun]

# Tools the ROADMAP listed as CUDA consumers that are not. DWPose is onnx-CPU by
# settled decision (LEDGER 19); wiring them would serialize CPU work against the
# other repos for nothing.
CPU_ONLY_TOOLS = ["lw_anat_probe.py", "lw_anat_metrics.py"]

# lw_first_pass.py spawns .venv-upscale and .venv-metrics children that DO
# acquire. If it acquired too, first pass would block on itself forever.
KNOWN_ORCHESTRATORS = ["lw_first_pass.py"]

# The one file allowed to spawn a subprocess while holding: upscale_ncnn runs
# realesrgan-ncnn-vulkan.exe, which is not a python interpreter and can never
# wait on the mutex. Any NEW entry here is a deadlock waiting to happen and must
# be justified in the same commit that adds it.
SPAWN_INSIDE_HOLD_ALLOWED = {"tools/lw_upscale.py"}


def _parse(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def _funcs(tree):
    """{qualified-ish name: node} for every def/async def in a module."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.setdefault(node.name, node)
    return out


def _is_lock_call(node):
    """True for `gpu_lock(...)` or `<anything>.gpu_lock(...)`.

    Attribute form matters: lw_clean_iopaint reaches the helper through its
    `import lw_clean_pass as C` alias.
    """
    if not isinstance(node, ast.Call):
        return False
    f = node.func
    if isinstance(f, ast.Name):
        return f.id == LOCK_NAME
    return isinstance(f, ast.Attribute) and f.attr == LOCK_NAME


def _holds(node):
    """Every `with gpu_lock(...)` statement lexically inside `node`."""
    found = []
    for sub in ast.walk(node):
        if not isinstance(sub, (ast.With, ast.AsyncWith)):
            continue
        if any(_is_lock_call(item.context_expr) for item in sub.items):
            found.append(sub)
    return found


# ---- the acquisitions exist, at the leaf, by structure ----------------------

def test_the_guard_has_something_to_guard():
    """An empty sweep must never read as a pass."""
    assert len(ACQUIRE_SITES) >= 15
    for fname, _ in ACQUIRE_SITES:
        assert (TOOLS / fname).is_file(), f"tools/{fname} does not exist"
    for fname, _cls, _meth in ACQUIRE_METHODS:
        assert (TOOLS / fname).is_file(), f"tools/{fname} does not exist"


@pytest.mark.parametrize("fname,func", ACQUIRE_SITES,
                         ids=[f"{f}:{fn}" for f, fn in ACQUIRE_SITES])
def test_cuda_leaf_acquires_gpu_mutex(fname, func):
    """The named leaf must open a `with gpu_lock(...)` block.

    AST, not a substring grep: a grep for "gpu_lock" passes on an import, on a
    comment, and on a call whose result is thrown away without ever entering a
    with-block - none of which hold anything.
    """
    tree = _parse(TOOLS / fname)
    fn = _funcs(tree).get(func)
    assert fn is not None, f"tools/{fname} has no function {func}()"
    assert _holds(fn), (
        f"tools/{fname}:{func}() does real CUDA work but never enters a "
        f"`with {LOCK_NAME}(...)` block - the GPU is unserialized there")


@pytest.mark.parametrize("fname,cls,meth", ACQUIRE_METHODS,
                         ids=[f"{f}:{c}.{m}" for f, c, m in ACQUIRE_METHODS])
def test_cuda_method_acquires_gpu_mutex(fname, cls, meth):
    """Same guard as the leaf one, resolved through the CLASS.

    Both open-clip scorers name their loader load(); keying on the bare name
    would check one of them twice and the other never.
    """
    tree = _parse(TOOLS / fname)
    klass = next((n for n in ast.walk(tree)
                  if isinstance(n, ast.ClassDef) and n.name == cls), None)
    assert klass is not None, f"tools/{fname} has no class {cls}"
    fn = next((n for n in klass.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == meth), None)
    assert fn is not None, f"tools/{fname}:{cls} has no method {meth}()"
    assert _holds(fn), (
        f"tools/{fname}:{cls}.{meth}() pulls CLIP weights onto the card but "
        f"never enters a `with {LOCK_NAME}(...)` block")


@pytest.mark.parametrize("fname,owner", sorted(BORROWERS.items()))
def test_borrowers_reuse_an_existing_copy_rather_than_forking_one(fname, owner):
    """A fifth/sixth/seventh copy of the helper is a drift surface, not safety.

    The four copies that DO exist are forced by the four-venv split (see
    LOCK_OWNERS). These three tools each run in a venv that already has an owner
    importable, so they borrow it - which is also why they do not appear in the
    LOCK_OWNERS parametrizations below.
    """
    src = (TOOLS / fname).read_text(encoding="utf-8")
    assert f"def {LOCK_NAME}(" not in src, (
        f"tools/{fname} forked its own copy of the helper; it must import "
        f"{owner}'s - one venv, one number")
    assert owner in src, (
        f"tools/{fname} acquires the GPU mutex but never mentions {owner}, so "
        f"it is not borrowing the copy this test claims it borrows")


def test_every_lock_owner_exposes_the_helper():
    for mod in LOCK_OWNERS:
        assert callable(getattr(mod, LOCK_NAME, None)), (
            f"{mod.__name__} does not expose {LOCK_NAME}")
        assert isinstance(getattr(mod, "GpuBusy", None), type), (
            f"{mod.__name__} does not expose the GpuBusy timeout surface")


def test_the_two_lw_clean_tools_reuse_one_copy_rather_than_forking_it():
    """Same venv, so they share - four copies is the venv split, not sloppiness.

    lw_clean_pass already imports from lw_g1_gate, and lw_clean_iopaint already
    imports lw_clean_pass as C. A fifth and sixth copy would be four chances for
    the timeout constant to drift apart inside a single venv.
    """
    assert cleanpass.gpu_lock is g1.gpu_lock
    assert cleanpass.GpuBusy is g1.GpuBusy
    assert iopaint.C.gpu_lock is g1.gpu_lock
    src = (TOOLS / "lw_clean_iopaint.py").read_text(encoding="utf-8")
    assert f"def {LOCK_NAME}(" not in src, (
        "lw_clean_iopaint forked its own copy of the helper; it reaches "
        "lw_clean_pass through the existing C alias")


# ---- the CPU fallback must NOT acquire -------------------------------------

class _FakeWinmutex:
    """Stand-in for ops/loop/winmutex.py that records what it was asked to do."""

    GPU_MUTEX = "Global\\LW_GPU"

    class MutexTimeout(RuntimeError):
        pass

    def __init__(self, raise_timeout=False):
        self.calls = []
        self.raise_timeout = raise_timeout

    def hold(self, name, *, timeout=None, log=None):
        self.calls.append({"name": name, "timeout": timeout})
        outer = self

        class _Ctx:
            def __enter__(self):
                if outer.raise_timeout:
                    raise outer.MutexTimeout(f"{name} not free within {timeout}s")
                if log:
                    log(f"winmutex: ACQUIRED {name}")
                return "handle"

            def __exit__(self, *exc):
                if log:
                    log(f"winmutex: RELEASED {name}")
                return False

        return _Ctx()


def _wire(mod, monkeypatch, raise_timeout=False):
    """Fake winmutex + capture the log sink.

    _gpu_log appends to logs/YYYY-MM-DD.log; a unit test must not write there,
    and capturing the lines is how the "logged, not a traceback" requirement is
    asserted rather than assumed.
    """
    fake = _FakeWinmutex(raise_timeout=raise_timeout)
    lines = []
    monkeypatch.setattr(mod, "_winmutex", lambda: fake)
    monkeypatch.setattr(mod, "_gpu_log", lines.append)
    return fake, lines


@pytest.mark.parametrize("mod", LOCK_OWNERS, ids=[m.__name__ for m in LOCK_OWNERS])
def test_cpu_path_does_not_take_the_mutex(mod, monkeypatch):
    """Serializing CPU work across three repos is pure loss, not safety."""
    fake, lines = _wire(mod, monkeypatch)
    with mod.gpu_lock("cpu") as handle:
        assert handle is None
    assert fake.calls == [], (
        f"{mod.__name__}.gpu_lock took the machine-wide GPU mutex on a CPU "
        f"fallback path")
    assert lines == []


@pytest.mark.parametrize("mod", LOCK_OWNERS, ids=[m.__name__ for m in LOCK_OWNERS])
def test_cuda_path_takes_the_mutex_and_logs_the_window(mod, monkeypatch):
    fake, lines = _wire(mod, monkeypatch)
    with mod.gpu_lock("cuda") as handle:
        assert handle == "handle"
    assert [c["name"] for c in fake.calls] == ["Global\\LW_GPU"]
    assert any("ACQUIRED" in ln for ln in lines)
    assert any("RELEASED" in ln for ln in lines)


def _cuda_uses(tree):
    """Real cuda USE in a module: `x.cuda` attributes and "cuda" string values.

    AST rather than a line grep because the wiring comments and module headers
    in these files discuss cuda at length, and a text sweep would read every one
    of those sentences as a GPU consumer. Docstrings are excluded for the same
    reason; comments never reach the AST at all.
    """
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)) or not body:
            continue
        head = body[0]
        if (isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant)
                and isinstance(head.value.value, str)):
            docs.add(id(head.value))

    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "cuda":
            hits.append(node)
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and "cuda" in node.value.lower() and id(node) not in docs):
            hits.append(node)
    return hits


def test_no_cuda_consumer_in_tools_is_left_unwired():
    """The census, as a guard instead of a claim in a commit message.

    Two sibling repos share this GPU and one of them is waiting on the answer to
    "is LW's CUDA lane fully serialized". Answering that by reading a report
    dated today is how it silently stops being true: the next tool that calls
    .to("cuda") reopens the unserialized lane and no existing test says a word.
    This turns the answer into something the suite re-derives every run.

    Exemptions are the two settled onnx-CPU tools (LEDGER 19), and the failure
    message names the two legitimate resolutions so nobody satisfies it by
    deleting the string.
    """
    wired = {f for f, _ in ACQUIRE_SITES} | {f for f, _c, _m in ACQUIRE_METHODS}
    # The exemption list is what makes this pass, so prove it is load-bearing:
    # a _cuda_uses that silently matched nothing would turn the whole sweep into
    # a green that means "I looked at no code".
    assert _cuda_uses(_parse(TOOLS / "lw_upscale.py")), (
        "_cuda_uses found no cuda in a known CUDA consumer - the detector is "
        "broken and this test is passing vacuously")

    exempt = wired | set(CPU_ONLY_TOOLS)
    unwired = []
    for py in sorted(TOOLS.glob("*.py")):
        if py.name in exempt:
            continue
        try:
            tree = _parse(py)
        except SyntaxError:
            continue
        hits = _cuda_uses(tree)
        if hits:
            unwired.append(f"{py.name}:{hits[0].lineno}")
    assert not unwired, (
        f"these tools touch cuda but acquire no GPU mutex: {unwired}. Either "
        f"wire the leaf and add it to ACQUIRE_SITES, or - if it genuinely runs "
        f"on CPU like the DWPose tools - add it to CPU_ONLY_TOOLS with the "
        f"evidence. Leaving it is an unserialized lane two other repos share.")


@pytest.mark.parametrize("fname", CPU_ONLY_TOOLS)
def test_cpu_only_tools_are_not_wired(fname):
    """DWPose is onnx-CPU (LEDGER 19). No cuda, therefore no mutex."""
    src = (TOOLS / fname).read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert not [n for n in ast.walk(tree) if _is_lock_call(n)], (
        f"tools/{fname} acquires the GPU mutex but runs on CPU")
    code_lines = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    assert not any("cuda" in ln for ln in code_lines), (
        f"tools/{fname} mentions cuda - if it really moved to GPU it needs "
        f"wiring, and the CPU-only claim in this test is now false")


# ---- degradation + timeout surface -----------------------------------------

@pytest.mark.parametrize("mod", LOCK_OWNERS, ids=[m.__name__ for m in LOCK_OWNERS])
def test_missing_winmutex_degrades_instead_of_raising(mod, monkeypatch):
    """A venv that cannot see winmutex must still be able to do its job.

    The mutex is a governor across repos, not a dependency of the tool. Crashing
    the upscaler because ops/loop/winmutex.py moved would trade a throughput
    problem for a broken pipeline.
    """
    lines = []
    monkeypatch.setattr(mod, "_gpu_log", lines.append)

    def _boom():
        raise ImportError("no winmutex here")

    monkeypatch.setattr(mod, "_winmutex", _boom)
    with mod.gpu_lock("cuda") as handle:
        assert handle is None
    assert any("UNSERIALIZED" in ln for ln in lines), (
        "a silent degrade leaves no evidence in the log the operator reads - "
        "the one case where nothing was serialized becomes the invisible one")


@pytest.mark.parametrize("mod", LOCK_OWNERS, ids=[m.__name__ for m in LOCK_OWNERS])
def test_mutex_timeout_surfaces_as_a_logged_gpu_busy(mod, monkeypatch):
    """A wedged holder must become a clean failure, not an invisible hang."""
    fake, lines = _wire(mod, monkeypatch, raise_timeout=True)
    with pytest.raises(mod.GpuBusy) as excinfo:
        with mod.gpu_lock("cuda"):
            pytest.fail("the body must not run when the mutex was never taken")
    assert isinstance(excinfo.value.__cause__, fake.MutexTimeout)
    assert any("TIMEOUT" in ln for ln in lines)


@pytest.mark.parametrize("mod", LOCK_OWNERS, ids=[m.__name__ for m in LOCK_OWNERS])
def test_timeout_is_finite_and_shorter_than_the_cycle_deadline(mod):
    """An infinite wait inside a headless cycle is an invisible hang.

    hold(timeout=None) waits forever, so a crashed-but-not-abandoned holder in
    another repo would burn the whole 5400s cycle with no log line explaining
    it. The bound has to leave the cycle enough room to report the failure and
    move on, which is what this asserts.
    """
    cfg = json.loads((ROOT / "ops" / "loop" / "config.json").read_text(encoding="utf-8"))
    deadline = cfg["cycle_deadline_sec"]
    t = mod.GPU_MUTEX_TIMEOUT_S
    assert 0 < t < deadline, f"{mod.__name__}.GPU_MUTEX_TIMEOUT_S={t} vs {deadline}"
    assert t <= deadline / 2, (
        "a timeout past half the cycle deadline leaves no room to report the "
        "failure and finish the cycle")


def test_timeout_is_the_same_number_in_every_tool():
    """Four copies of the helper, one number - a per-tool drift is a bug."""
    values = {mod.__name__: mod.GPU_MUTEX_TIMEOUT_S for mod in LOCK_OWNERS}
    assert len(set(values.values())) == 1, values


def test_path_binding_reaches_the_real_winmutex():
    """The _bind-by-path form must actually resolve, not just be plausible.

    ops/loop has no __init__.py and none of the four venvs has the repo root on
    sys.path, so a package-style `from ops.loop import winmutex` would ImportError
    everywhere the tools actually run - and, because the helper degrades on
    import failure, it would do so SILENTLY.
    """
    wm = g1._winmutex()
    assert wm.GPU_MUTEX == "Global\\LW_GPU"
    assert issubclass(wm.MutexTimeout, RuntimeError)


# ---- the self-deadlock guards ----------------------------------------------

# Widened 2026-08-01. The first version matched `subprocess.<attr>(...)` and
# nothing else, so three real shapes walked straight past it: os.system, a
# `from subprocess import run` binding, and - the one that actually mattered
# here - a hold that calls a LOCAL helper which does the spawning one frame
# down. lw_gen_run._shell_stage and lw_gen_weaponpass._build_real_gate are both
# exactly that shape, so the widening is not hypothetical.
#
# WHAT IT STILL CANNOT SEE, stated rather than papered over: the weapon pass
# invokes its shell-out through a CLOSURE held in a local variable
# (`active_gate(crop_pil)`), and no lexical pass can resolve a variable to the
# function it was assigned. That gap is why
# test_weaponpass_does_not_hold_across_its_gate_subprocess exists as a named,
# per-file guard rather than trusting this sweep to cover everything.
_SUBPROCESS_SPAWNERS = {"run", "Popen", "call", "check_call", "check_output",
                        "getoutput", "getstatusoutput"}
_OS_SPAWNERS = {"system", "popen", "startfile", "execv", "execve", "execvp",
                "execvpe", "spawnv", "spawnve", "spawnl", "spawnle",
                "posix_spawn", "posix_spawnp", "fork", "forkpty"}


def _spawn_imports(tree):
    """(module-alias -> real module, {bare names bound to a spawn function})."""
    aliases = {}
    bare = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in ("subprocess", "os"):
                    aliases[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom):
            if node.module == "subprocess":
                pool = _SUBPROCESS_SPAWNERS
            elif node.module == "os":
                pool = _OS_SPAWNERS
            else:
                continue
            for a in node.names:
                if a.name in pool:
                    bare.add(a.asname or a.name)
    return aliases, bare


def _spawn_calls(node, aliases=None, bare=frozenset()):
    """Every process-spawning call lexically inside `node`."""
    if aliases is None:
        aliases = {"subprocess": "subprocess", "os": "os"}
    out = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            mod = aliases.get(f.value.id)
            if mod == "subprocess":
                out.append(sub)
            elif mod == "os" and f.attr in _OS_SPAWNERS:
                out.append(sub)
        elif isinstance(f, ast.Name) and f.id in bare:
            out.append(sub)
    return out


def _local_spawners(tree, aliases, bare):
    """Module-local function names that reach a spawn, transitively.

    Deliberately over-approximating: a function whose NESTED def spawns counts
    as spawning, because calling the outer one is how you get the inner one.
    Over-approximating is the safe direction - a false positive costs one
    justified SPAWN_INSIDE_HOLD_ALLOWED entry, a false negative costs a hang.
    """
    funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.setdefault(node.name, node)
    reach = {n for n, fn in funcs.items() if _spawn_calls(fn, aliases, bare)}
    changed = True
    while changed:
        changed = False
        for name, fn in funcs.items():
            if name in reach:
                continue
            for sub in ast.walk(fn):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id in reach):
                    reach.add(name)
                    changed = True
                    break
    return reach


def _indirect_spawn_calls(node, spawners):
    """Calls to a module-local function that reaches a spawn one frame down."""
    return [sub for sub in ast.walk(node)
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            and sub.func.id in spawners]


def _scan_files():
    for base in (ROOT / "tools", ROOT / "ops"):
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            yield py


def test_no_python_child_is_spawned_inside_a_hold():
    """The self-deadlock trap, expressed structurally.

    Windows named mutexes are re-entrant per thread, not per process tree. A
    child that waits on a mutex its parent already holds blocks forever, and
    "forever" inside a headless cycle looks exactly like a hung machine. Rather
    than trying to decide from AST whether an argv[0] is a python interpreter,
    this asserts the strict rule with one documented exception.
    """
    offenders = []
    for py in _scan_files():
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:  # py_compile's job, not this test's
            continue
        rel = py.relative_to(ROOT).as_posix()
        if rel in SPAWN_INSIDE_HOLD_ALLOWED:
            continue
        aliases, bare = _spawn_imports(tree)
        spawners = _local_spawners(tree, aliases, bare)
        for hold in _holds(tree):
            direct = _spawn_calls(hold, aliases, bare)
            indirect = _indirect_spawn_calls(hold, spawners)
            if direct or indirect:
                via = ",".join(sorted({c.func.id for c in indirect})) or "direct"
                offenders.append(f"{rel}:{hold.lineno} (via {via})")
    assert not offenders, (
        f"subprocess spawned while holding GPU_MUTEX at {offenders} - if that "
        f"child ever acquires the same mutex it blocks forever. Move the spawn "
        f"outside the hold, or add the file to SPAWN_INSIDE_HOLD_ALLOWED with "
        f"the reason it can never acquire.")


@pytest.mark.parametrize("fname", KNOWN_ORCHESTRATORS)
def test_known_orchestrators_do_not_acquire(fname):
    """lw_first_pass spawns two venv pythons that each acquire; it must not.

    Acquisition belongs at the leaf anyway - that is the only placement under
    which a hand-run `python lw_upscale.py` is protected, which is exactly what
    the winmutex docstring promises.
    """
    src = (TOOLS / fname).read_text(encoding="utf-8")
    tree = ast.parse(src)
    assert not [n for n in ast.walk(tree) if _is_lock_call(n)], (
        f"tools/{fname} is an ORCHESTRATOR - it spawns venv pythons that "
        f"acquire GPU_MUTEX themselves, so acquiring here deadlocks first pass "
        f"against its own child")
    assert "winmutex" not in src and "GPU_MUTEX" not in src


def test_gen_run_does_not_hold_across_its_qa_subprocess():
    """lw_gen_run is both a CUDA worker and an orchestrator - the one hybrid.

    Its round loop calls _shell_stage(metrics_py, lw_gen_qa.py), and lw_gen_qa
    is itself a CUDA consumer. So the generation hold cannot be widened to span
    the loop: that is precisely the parent-holds-while-child-waits deadlock.
    The cost is that the SDXL pipe stays resident on the card between holds -
    accepted, because the alternative is a hang.
    """
    tree = _parse(TOOLS / "lw_gen_run.py")
    funcs = _funcs(tree)
    for name in ("run", "main"):
        fn = funcs.get(name)
        assert fn is not None, f"lw_gen_run has no {name}()"
        assert not _holds(fn), (
            f"lw_gen_run.{name}() opened a gpu_lock block - it spawns "
            f"lw_gen_qa in .venv-metrics from inside its round loop, which "
            f"would deadlock the parent against its own child")


def test_weaponpass_does_not_hold_across_its_gate_subprocess():
    """The SECOND hybrid, and the one the generic sweep cannot see.

    run_pass()'s clip lane alternates _inpaint_roll (CUDA, in process) with
    active_gate(crop_pil), and the real gate closure shells
    `lw_gen_qa.py --weapon-crop` into .venv-metrics. lw_gen_qa now acquires
    GPU_MUTEX itself, so a hold widened over that loop is the textbook
    parent-holds-while-child-waits deadlock - and because the gate arrives as a
    closure in a local variable, no lexical sweep can resolve it. Hence this
    named guard: the acquisitions live in _build_real_inpainter and in the real
    _inpaint closure, both of which return before the gate is ever called.

    The accepted cost is the same one lw_gen_run pays: the inpaint pipe stays
    resident on the card between rolls while the mutex is free.
    """
    tree = _parse(TOOLS / "lw_gen_weaponpass.py")
    funcs = _funcs(tree)
    for name in ("weapon_pass", "main", "_build_real_gate"):
        fn = funcs.get(name)
        assert fn is not None, f"lw_gen_weaponpass has no {name}()"
        assert not _holds(fn), (
            f"lw_gen_weaponpass.{name}() opened a gpu_lock block - the weapon "
            f"gate shells lw_gen_qa.py into .venv-metrics, and lw_gen_qa "
            f"acquires the same mutex, so the parent would wait on its child "
            f"forever")


def test_inpaint_roll_itself_stays_unheld_so_stub_tests_take_no_machine_mutex():
    """_inpaint_roll is called with an INJECTED inpainter throughout the suite.

    tests/test_lw_gen_weaponpass.py drives the whole fix loop with a stub
    inpainter, so a hold placed in _inpaint_roll would make an ordinary CI run
    grab the machine-wide GPU mutex once per roll - and block for the full
    timeout whenever a real generation happened to be running. The hold belongs
    in the REAL closure, which a stub never reaches.
    """
    tree = _parse(TOOLS / "lw_gen_weaponpass.py")
    fn = _funcs(tree).get("_inpaint_roll")
    assert fn is not None
    assert not _holds(fn), (
        "lw_gen_weaponpass._inpaint_roll acquires GPU_MUTEX, but the test "
        "suite calls it with a stub inpainter - CI would take a machine-wide "
        "lock it has no business taking")


def test_the_spawn_guard_catches_the_shapes_it_claims_to_catch():
    """Self-test: an assertion nobody can prove is an assertion nobody trusts.

    The original guard matched `subprocess.<attr>(...)` only. Each snippet here
    is a real way to start a process that the original form let through, so this
    is what makes the widening honest rather than decorative.
    """
    cases = {
        "os.system": "import os\nwith gpu_lock('cuda'):\n    os.system('py x.py')\n",
        "from-import": ("from subprocess import run\n"
                        "with gpu_lock('cuda'):\n    run(['py', 'x.py'])\n"),
        "aliased module": ("import subprocess as sp\n"
                           "with gpu_lock('cuda'):\n    sp.Popen(['py'])\n"),
    }
    for label, src in cases.items():
        tree = ast.parse(src)
        aliases, bare = _spawn_imports(tree)
        holds = _holds(tree)
        assert holds, label
        assert _spawn_calls(holds[0], aliases, bare), (
            f"the spawn guard does not see the {label} form")

    indirect = (
        "import subprocess\n"
        "def _shell(cmd):\n"
        "    subprocess.run(cmd)\n"
        "def work():\n"
        "    with gpu_lock('cuda'):\n"
        "        _shell(['py', 'x.py'])\n"
    )
    tree = ast.parse(indirect)
    aliases, bare = _spawn_imports(tree)
    spawners = _local_spawners(tree, aliases, bare)
    assert "_shell" in spawners and "work" in spawners
    hold = _holds(tree)[0]
    assert not _spawn_calls(hold, aliases, bare), (
        "the indirect case must be invisible to the DIRECT matcher - otherwise "
        "this test is not proving the transitive layer does anything")
    assert _indirect_spawn_calls(hold, spawners), (
        "a hold that calls a local helper which spawns is the exact shape "
        "lw_gen_run._shell_stage has, and the guard missed it")

    clean = ("import subprocess\n"
             "def _shell(cmd):\n    subprocess.run(cmd)\n"
             "def work():\n    with gpu_lock('cuda'):\n        pass\n"
             "    _shell(['py'])\n")
    tree = ast.parse(clean)
    aliases, bare = _spawn_imports(tree)
    spawners = _local_spawners(tree, aliases, bare)
    assert not _indirect_spawn_calls(_holds(tree)[0], spawners), (
        "a spawn OUTSIDE the hold is the correct pattern and must not be "
        "flagged - a guard that fires on the fix teaches people to disable it")


# ---- lw_gen_qa: one hold per batch, none on the CPU fallback ----------------

class _StubScore:
    subject_cos = 0.9
    off_cos = 0.1
    aesthetic = 0.9
    lap_var = 500.0
    weapon_cos = 0.9
    weapon_off = 0.1


class _StubScorer:
    """Stands in for ClipScorer. `device` is what score_batch keys the hold on."""

    def __init__(self, device):
        self.device = device
        self.calls = 0

    def __call__(self, path):
        self.calls += 1
        return _StubScore()


def _qa_batch(tmp_path, n=3):
    batch = tmp_path / "batch"
    batch.mkdir()
    manifest = {"subject": "Vayne", "candidates": [
        {"file": f"cand_{i:02d}.png", "round": 1, "seed": i} for i in range(n)]}
    (batch / "gen_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return batch


def test_qa_batch_takes_exactly_one_hold_for_the_whole_candidate_list(tmp_path,
                                                                     monkeypatch):
    """Per-candidate acquire/release would hand the card away mid-batch.

    The CLIP model is resident for the whole batch; dropping the mutex between
    two candidates lets another repo start a load LW is about to interrupt. One
    hold is safe here precisely because lw_gen_qa spawns nothing - unlike the
    two hybrids, it has no shell-out to stay outside of.
    """
    fake, lines = _wire(g1, monkeypatch)
    scorer = _StubScorer("cuda")
    genqa.score_batch(str(_qa_batch(tmp_path, n=3)), scorer=scorer, config={})
    assert scorer.calls == 3
    assert [c["name"] for c in fake.calls] == ["Global\\LW_GPU"], (
        f"expected ONE hold for the batch, got {len(fake.calls)}")
    assert any("ACQUIRED" in ln for ln in lines)


def test_qa_batch_on_a_cpu_scorer_takes_no_mutex(tmp_path, monkeypatch):
    """The stub scorer the rest of the suite injects must stay lock-free too.

    Every other lw_gen_qa test drives score_batch with a bare stub. If the hold
    were unconditional, an ordinary CI run would take a machine-wide lock and
    could sit on it while a real generation waited.
    """
    fake, lines = _wire(g1, monkeypatch)
    genqa.score_batch(str(_qa_batch(tmp_path, n=2)),
                      scorer=_StubScorer("cpu"), config={})
    assert fake.calls == []
    assert lines == []


def test_qa_batch_with_a_deviceless_stub_defaults_to_cpu(tmp_path, monkeypatch):
    """A plain function has no .device - it must read as CPU, not as CUDA.

    tests/test_lw_gen_qa.py injects exactly that. Defaulting the unknown case to
    "cuda" would be the fail-dangerous direction: it takes a real lock on the
    strength of an attribute that is not there.
    """
    fake, _lines = _wire(g1, monkeypatch)
    genqa.score_batch(str(_qa_batch(tmp_path, n=2)),
                      scorer=lambda path: _StubScore(), config={})
    assert fake.calls == []


def test_weapon_crop_report_holds_only_for_a_cuda_scorer(monkeypatch):
    fake, _lines = _wire(g1, monkeypatch)
    genqa.weapon_crop_report("ignored.png", _StubScorer("cpu"))
    assert fake.calls == []
    genqa.weapon_crop_report("ignored.png", _StubScorer("cuda"))
    assert [c["name"] for c in fake.calls] == ["Global\\LW_GPU"]


# ---- nesting + timeout semantics, against the REAL winmutex -----------------

class _NamedShim:
    """The real winmutex, renamed.

    Exercising nesting against the live Global\\LW_GPU would contend with any
    generation actually running on this machine, so these tests take a
    process-unique name through the same code path instead. The primitive under
    test is identical; only the string differs.
    """

    def __init__(self, real, name):
        self._real = real
        self.GPU_MUTEX = name
        self.MutexTimeout = real.MutexTimeout

    def hold(self, name, *, timeout=None, log=None):
        return self._real.hold(name, timeout=timeout, log=log)


def test_nested_same_thread_acquisition_does_not_deadlock(monkeypatch):
    """lw_clean_sdxl.run_worklist holds, then calls into the weapon pass.

    lw_clean_sdxl imports lw_gen_weaponpass._build_real_inpainter IN-PROCESS
    while run_worklist holds the mutex, and _build_real_inpainter now acquires
    too - so that is a nested same-thread acquisition. A Windows named mutex is
    recursive (N acquires need N releases) and the `with` blocks are symmetric,
    so it is safe; a naive non-recursive lock would wedge right here. The
    non-Windows branch is a no-op, so CI alone would never tell you either way -
    which is exactly why this is pinned on the real primitive.

    The short timeout is the point: on a non-recursive lock this FAILS in five
    seconds instead of hanging the suite for the production 1800.
    """
    real = g1._winmutex()
    name = f"Global\\LW_GPU_NESTTEST_{os.getpid()}"
    for mod in (g1, genrun):
        monkeypatch.setattr(mod, "_winmutex", lambda r=real, n=name: _NamedShim(r, n))
        monkeypatch.setattr(mod, "_gpu_log", lambda _msg: None)
        monkeypatch.setattr(mod, "GPU_MUTEX_TIMEOUT_S", 5.0)

    reached = False
    with g1.gpu_lock("cuda"):
        with genrun.gpu_lock("cuda"):
            with g1.gpu_lock("cuda"):
                reached = True
    assert reached, "a nested same-thread acquire never returned"

    # And the mutex is genuinely free afterwards - N releases for N acquires.
    with g1.gpu_lock("cuda"):
        pass


def test_the_timeout_bounds_the_WAIT_not_the_HOLD(monkeypatch):
    """Why the LoRA trainer keeps the shared 1800 instead of a bespoke number.

    winmutex.hold passes `timeout` to WaitForSingleObject (winmutex.py:96-101),
    so it caps how long a caller waits to ACQUIRE - it is not a deadline on the
    body. A multi-hour training hold therefore cannot time itself out, and the
    argument for giving that tool a longer constant does not survive contact
    with the primitive. Pinned here because the day someone "fixes" hold() to
    bound the body instead, a legitimate overnight LoRA run starts dying at the
    30 minute mark with no other test noticing.
    """
    real = g1._winmutex()
    name = f"Global\\LW_GPU_WAITTEST_{os.getpid()}"
    monkeypatch.setattr(g1, "_winmutex", lambda: _NamedShim(real, name))
    monkeypatch.setattr(g1, "_gpu_log", lambda _msg: None)
    monkeypatch.setattr(g1, "GPU_MUTEX_TIMEOUT_S", 0.01)

    with g1.gpu_lock("cuda"):
        time.sleep(0.2)  # 20x the timeout, uncontended


def test_the_lora_trainer_inherits_the_shared_timeout_by_import(monkeypatch):
    """No bespoke constant, so no way for it to drift out of the shared number.

    The trainer borrows lw_gen_run's helper wholesale rather than declaring its
    own GPU_MUTEX_TIMEOUT_S, which is what makes
    test_timeout_is_the_same_number_in_every_tool cover it for free.
    """
    src = (TOOLS / "lw_gen_train_weapon_lora.py").read_text(encoding="utf-8")
    assert "GPU_MUTEX_TIMEOUT_S =" not in src, (
        "the trainer declared its own timeout - a fifth number to keep in sync")
    trainer = __import__("lw_gen_train_weapon_lora")
    assert trainer.gpu_lock is genrun.gpu_lock
    assert trainer.GpuBusy is genrun.GpuBusy
