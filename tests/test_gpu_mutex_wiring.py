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
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import lw_clean_iopaint as iopaint  # noqa: E402
import lw_clean_pass as cleanpass  # noqa: E402
import lw_clean_sdxl as sdxl  # noqa: E402
import lw_g1_gate as g1  # noqa: E402
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
]

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
    assert len(ACQUIRE_SITES) >= 10
    for fname, _ in ACQUIRE_SITES:
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

def _spawn_calls(node):
    """Every subprocess.<spawn>(...) call lexically inside `node`."""
    out = []
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        f = sub.func
        if (isinstance(f, ast.Attribute)
                and isinstance(f.value, ast.Name) and f.value.id == "subprocess"):
            out.append(sub)
    return out


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
        for hold in _holds(tree):
            if _spawn_calls(hold) and rel not in SPAWN_INSIDE_HOLD_ALLOWED:
                offenders.append(f"{rel}:{hold.lineno}")
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
