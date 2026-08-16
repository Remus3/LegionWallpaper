"""Full-mesh multi-angle headless render of a LoL champion skin (.skn).

Chain: CommunityDragon raw .skn + _tx_cm.png -> pyritofile SKN parse -> moderngl
standalone context -> offscreen FBO -> Pillow PNG. NO bone isolation: the whole
mesh is drawn, textured.

Runs in .venv-poc (moderngl + pyritofile + numpy + pillow), NOT the main env:
  C:\\LegionWallpaper\\.venv-poc\\Scripts\\python.exe tools/lw_render_skn.py --help

Provenance: rebuilt 2026-08-15 from the recipe in docs/research/crossbow_render_poc.md
after the original POC code was lost with an ephemeral scratchpad (docs/LEDGER.md:2861).
Preserved here so the third loss does not happen.

ACQUIRE (not done by this script - fetch the two files first):
  https://raw.communitydragon.org/latest/game/assets/characters/<champ>/skins/<dir>/<mesh>.skn
  https://raw.communitydragon.org/latest/game/assets/characters/<champ>/skins/<dir>/<mesh>_tx_cm.png
CDragon returns 403 to a bare urllib request - a User-Agent header is REQUIRED.
Discover per-skin dirs + mesh names by fetching the skin dir URL and grepping href=.
Every skin ships its own .skn; none reuse base.

KNOWN LIMITS (measured 2026-08-15, both proven on skin03 dragonslayer + skin02
aristocrat, 12 yaw angles each at 1024px, ~0.035s per render on an RTX 5070):
- BIND POSE ONLY. CDragon 404s the .skl, so there is no skeleton and no posing.
  You get the one stance baked into the mesh, from any camera angle.
- Single-texture assumption. Both proven skins were one submesh / one _tx_cm. A
  multi-material skin needs per-submesh texture binding, not implemented here.
- No alpha-test / cutout and no backface culling. A skin with alpha-cutout hair or
  foliage cards will render those quads opaque.
- Framing is bounding-sphere fit, so a raised weapon inflates the bbox and shrinks
  the subject in frame.

DO NOT read this as a training-data pipeline for a generative LoRA. Renders are
separable from painted splash art at AUC 1.0 on a single scalar (laplacian
variance / unique-RGB / gray-128 fraction, measured 2026-08-15) and the
per-champion LoRA method failed on real splashes anyway. The live consumer is a
DISCRIMINATIVE one (the m1 canonicity gate), where matched provenance is the point.
"""
import argparse
import math
import os
import sys
import time

import numpy as np

DEFAULT_SIZE = 1024
DEFAULT_ANGLES = 12
DEFAULT_FOVY = 35.0
# Neutral gray, matching _NEUTRAL_FILL in tools/lw_gen_train_weapon_lora.py so a
# render and a training-crop canvas share a background.
BG_LEVEL = 128
# UV vertical flip is FALSE for CDragon textures - True comes out garbled.
FLIP_V = False

VS = """
#version 330
uniform mat4 mvp;
in vec3 in_pos;
in vec3 in_nrm;
in vec2 in_uv;
out vec3 v_nrm;
out vec2 v_uv;
void main() {
    gl_Position = mvp * vec4(in_pos, 1.0);
    v_nrm = in_nrm;
    v_uv = in_uv;
}
"""

FS = """
#version 330
uniform sampler2D tex0;
uniform int use_tex;
in vec3 v_nrm;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec3 n = normalize(v_nrm);
    float lam = 0.55 + 0.45 * max(dot(n, normalize(vec3(0.35, 0.55, 0.75))), 0.0);
    vec3 base = (use_tex == 1) ? texture(tex0, v_uv).rgb : vec3(0.75);
    f_color = vec4(base * lam, 1.0);
}
"""


def look_at(eye, target, up):
    """Right-handed view matrix. Pure numpy - no GL context needed."""
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.identity(4, dtype="f4")
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m


def perspective(fovy_deg, aspect, znear, zfar):
    """Standard GL perspective projection. Pure numpy - no GL context needed."""
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    m = np.zeros((4, 4), dtype="f4")
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (zfar + znear) / (znear - zfar)
    m[2, 3] = (2 * zfar * znear) / (znear - zfar)
    m[3, 2] = -1.0
    return m


def orbit_eye(center, radius, dist, yaw, height_frac=0.15):
    """Camera position for one yaw step of a level orbit. Pure numpy."""
    return center + np.array(
        [dist * math.sin(yaw), radius * height_frac, dist * math.cos(yaw)],
        dtype="f4",
    )


def bounds(pos):
    """Return (center, radius) of the mesh bounding sphere. Pure numpy."""
    lo = pos.min(axis=0)
    hi = pos.max(axis=0)
    center = (lo + hi) / 2.0
    radius = float(np.linalg.norm(hi - lo) / 2.0)
    return center, radius


def load_mesh(path):
    """Parse a .skn into (skn, positions, normals, uvs, indices).

    pyritofile is imported lazily so the pure-math helpers above stay importable
    outside .venv-poc (the test suite exercises them without a GL stack).
    """
    from pyritofile import SKN

    def vec3(v):
        return (float(v.x), float(v.y), float(v.z))

    def vec2(v):
        return (float(v.x), float(v.y))

    skn = SKN()
    skn.read(path)
    pos = np.array([vec3(v.position) for v in skn.vertices], dtype="f4")
    nrm = np.array([vec3(v.normal) for v in skn.vertices], dtype="f4")
    uv = np.array([vec2(v.uv) for v in skn.vertices], dtype="f4")
    idx = np.array(skn.indices, dtype="i4")
    return skn, pos, nrm, uv, idx


def render(skn_path, tex_path, out_dir, size, n_angles, fovy, stem, quiet=False):
    """Render n_angles yaw views of the whole mesh. Returns the list of paths."""
    import moderngl
    from PIL import Image

    def say(msg):
        if not quiet:
            print(msg)

    os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    skn, pos, nrm, uv, idx = load_mesh(skn_path)
    say(f"PARSE ok  version={skn.version} verts={len(pos)} tris={len(idx) // 3} "
        f"submeshes={len(skn.submeshes)}  {time.time() - t0:.3f}s")
    if len(skn.submeshes) > 1:
        say(f"WARN  {len(skn.submeshes)} submeshes - this renderer binds ONE "
            f"texture for all of them")

    center, radius = bounds(pos)
    say(f"BBOX center={center} radius={radius:.2f}")

    t0 = time.time()
    ctx = moderngl.create_standalone_context()
    say(f"GL   ok  {time.time() - t0:.3f}s  renderer={ctx.info.get('GL_RENDERER')} "
        f"version={ctx.info.get('GL_VERSION')}")

    img = Image.open(tex_path).convert("RGB")
    if FLIP_V:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    say(f"TEX  ok  size={img.size}")
    tex = ctx.texture(img.size, 3, img.tobytes())
    tex.build_mipmaps()
    tex.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
    tex.use(0)

    prog = ctx.program(vertex_shader=VS, fragment_shader=FS)
    prog["tex0"].value = 0
    prog["use_tex"].value = 1

    inter = np.hstack([pos, nrm, uv]).astype("f4")
    vbo = ctx.buffer(inter.tobytes())
    ibo = ctx.buffer(idx.astype("i4").tobytes())
    vao = ctx.vertex_array(prog, [(vbo, "3f 3f 2f", "in_pos", "in_nrm", "in_uv")], ibo)

    fbo = ctx.framebuffer(
        color_attachments=[ctx.texture((size, size), 4)],
        depth_attachment=ctx.depth_renderbuffer((size, size)),
    )
    fbo.use()
    ctx.enable(moderngl.DEPTH_TEST)

    dist = radius * 2.6
    proj = perspective(fovy, 1.0, max(0.05, radius * 0.05), dist + radius * 4.0)
    up = np.array([0.0, 1.0, 0.0], dtype="f4")
    bg = (BG_LEVEL / 255.0, BG_LEVEL / 255.0, BG_LEVEL / 255.0, 1.0)

    written = []
    times = []
    for i in range(n_angles):
        yaw = 2.0 * math.pi * i / n_angles
        t0 = time.time()
        eye = orbit_eye(center, radius, dist, yaw)
        mvp = (proj @ look_at(eye.astype("f4"), center.astype("f4"), up)).astype("f4")
        prog["mvp"].write(np.ascontiguousarray(mvp.T).tobytes())
        fbo.clear(*bg)
        vao.render(moderngl.TRIANGLES)
        data = fbo.read(components=3, alignment=1)
        out = Image.frombytes("RGB", (size, size), data).transpose(Image.FLIP_TOP_BOTTOM)
        deg = int(round(math.degrees(yaw)))
        name = os.path.join(out_dir, f"{stem}_yaw{deg:03d}.png")
        out.save(name)
        dt = time.time() - t0
        times.append(dt)
        written.append(name)
        arr = np.asarray(out, dtype=np.float32)
        nonbg = float(np.mean(np.abs(arr - float(BG_LEVEL)).max(axis=2) > 6))
        say(f"RENDER {os.path.basename(name):<44s} {dt:.3f}s  nonbg_frac={nonbg:.4f}")

    if times:
        say(f"TOTAL {len(times)} angles  mean={sum(times) / len(times):.3f}s  "
            f"min={min(times):.3f}s  max={max(times):.3f}s")
    return written


def build_parser():
    p = argparse.ArgumentParser(
        description="Full-mesh multi-angle headless render of a LoL .skn (bind pose only).",
    )
    p.add_argument("--skn", required=True, help="path to the .skn mesh")
    p.add_argument("--tex", required=True, help="path to the _tx_cm.png body texture")
    p.add_argument("--out", required=True, help="output directory for the PNGs")
    p.add_argument("--stem", default=None, help="output filename stem (default: .skn basename)")
    p.add_argument("--size", type=int, default=DEFAULT_SIZE)
    p.add_argument("--angles", type=int, default=DEFAULT_ANGLES)
    p.add_argument("--fovy", type=float, default=DEFAULT_FOVY)
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    for path in (args.skn, args.tex):
        if not os.path.isfile(path):
            print(f"ERROR missing input: {path}", file=sys.stderr)
            return 2
    if args.angles < 1:
        print("ERROR --angles must be >= 1", file=sys.stderr)
        return 2
    stem = args.stem or os.path.splitext(os.path.basename(args.skn))[0]
    render(args.skn, args.tex, args.out, args.size, args.angles, args.fovy, stem, args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
