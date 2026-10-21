"""Geometry kernel for the 3D viewer.

Builders construct solids from parameters with exact coordinates. The
validator checks structural sanity (references, planarity, outward face
orientation) and verifies geometric claims (distances, right angles,
parallelism, midpoints) numerically. A solid that fails validation must
never reach the renderer.
"""

import math

TOL = 1e-6


# ---------- small vector helpers (tuples of 3 floats) ----------

def _sub(p, q):
    return (p[0] - q[0], p[1] - q[1], p[2] - q[2])


def _dot(p, q):
    return p[0] * q[0] + p[1] * q[1] + p[2] * q[2]


def _cross(p, q):
    return (
        p[1] * q[2] - p[2] * q[1],
        p[2] * q[0] - p[0] * q[2],
        p[0] * q[1] - p[1] * q[0],
    )


def _norm(p):
    return math.sqrt(_dot(p, p))


def _dist(p, q):
    return _norm(_sub(p, q))


def _centroid(points):
    n = len(points)
    return tuple(sum(p[i] for p in points) / n for i in range(3))


# ---------- builders: kind + params -> vertices / faces / aux ----------

def _cuboid_oadb_cfme(a=3.0, b=4.0, c=2.5):
    """Textbook Oxyz box (Bai 7): base OADB, top CFME.

    O is the origin, A on Ox, D on Oy, B the far base corner.
    C is above O, F above A, M above D, E above B — so the diagonals read
    OM = OA + OB + OC. (Regression fixture: M must sit above D.)
    """
    vertices = {
        "O": (0.0, 0.0, 0.0),
        "A": (a, 0.0, 0.0),
        "D": (0.0, b, 0.0),
        "B": (a, b, 0.0),
        "C": (0.0, 0.0, c),
        "F": (a, 0.0, c),
        "M": (0.0, b, c),
        "E": (a, b, c),
    }
    faces = [
        ["O", "D", "B", "A"],  # z = 0
        ["C", "F", "E", "M"],  # z = c
        ["O", "A", "F", "C"],  # y = 0
        ["D", "M", "E", "B"],  # y = b
        ["O", "C", "M", "D"],  # x = 0
        ["A", "B", "E", "F"],  # x = a
    ]
    return vertices, faces, [], []


def _cube(s=2.0):
    vertices = {
        "A": (0.0, 0.0, 0.0),
        "B": (s, 0.0, 0.0),
        "C": (s, s, 0.0),
        "D": (0.0, s, 0.0),
        "A'": (0.0, 0.0, s),
        "B'": (s, 0.0, s),
        "C'": (s, s, s),
        "D'": (0.0, s, s),
    }
    faces = [
        ["A", "D", "C", "B"],
        ["A'", "B'", "C'", "D'"],
        ["A", "B", "B'", "A'"],
        ["D", "D'", "C'", "C"],
        ["A", "A'", "D'", "D"],
        ["B", "C", "C'", "B'"],
    ]
    return vertices, faces, [], []


def _square_pyramid(a=4.0, h=3.0):
    """S.ABCD with square base ABCD and apex S over the base centre O."""
    vertices = {
        "A": (0.0, 0.0, 0.0),
        "B": (a, 0.0, 0.0),
        "C": (a, a, 0.0),
        "D": (0.0, a, 0.0),
        "S": (a / 2, a / 2, h),
        "O": (a / 2, a / 2, 0.0),  # auxiliary: base centre / foot of SO
    }
    faces = [
        ["A", "D", "C", "B"],
        ["A", "B", "S"],
        ["B", "C", "S"],
        ["C", "D", "S"],
        ["D", "A", "S"],
    ]
    return vertices, faces, ["O"], [["S", "O"]]


def _triangular_prism(a=3.0, b=4.0, h=2.5):
    """Right prism on a right triangle ABC (right angle at A), height h."""
    vertices = {
        "A": (0.0, 0.0, 0.0),
        "B": (a, 0.0, 0.0),
        "C": (0.0, b, 0.0),
        "A'": (0.0, 0.0, h),
        "B'": (a, 0.0, h),
        "C'": (0.0, b, h),
    }
    faces = [
        ["A", "C", "B"],
        ["A'", "B'", "C'"],
        ["A", "B", "B'", "A'"],
        ["A", "A'", "C'", "C"],
        ["B", "C", "C'", "B'"],
    ]
    return vertices, faces, [], []


_BUILDERS = {
    "cuboid": _cuboid_oadb_cfme,
    "cube": _cube,
    "square_pyramid": _square_pyramid,
    "triangular_prism": _triangular_prism,
}


def _edges_from_faces(faces):
    edges = set()
    for face in faces:
        for i in range(len(face)):
            u, v = face[i], face[(i + 1) % len(face)]
            edges.add(tuple(sorted((u, v))))
    return sorted(edges)


# ---------- validation gate ----------

def validate_solid(vertices, faces):
    """Return a list of structural problems; empty means the solid is sound."""
    problems = []
    for name, p in vertices.items():
        if len(p) != 3 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in p):
            problems.append(f"vertex {name}: bad coordinates {p}")
    if problems:
        return problems

    centre = _centroid(list(vertices.values()))
    for face in faces:
        if len(face) < 3:
            problems.append(f"face {face}: fewer than 3 vertices")
            continue
        missing = [n for n in face if n not in vertices]
        if missing:
            problems.append(f"face {face}: unknown vertices {missing}")
            continue
        pts = [vertices[n] for n in face]
        if len(pts) >= 4:
            triple = _dot(_sub(pts[1], pts[0]), _cross(_sub(pts[2], pts[0]), _sub(pts[3], pts[0])))
            scale = max(1.0, _norm(_sub(pts[1], pts[0])) ** 3)
            if abs(triple) / scale > 1e-6:
                problems.append(f"face {face}: not planar")
        # outward orientation via Newell's method
        nx = ny = nz = 0.0
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            nx += (p[1] - q[1]) * (p[2] + q[2])
            ny += (p[2] - q[2]) * (p[0] + q[0])
            nz += (p[0] - q[0]) * (p[1] + q[1])
        fc = _centroid(pts)
        if _dot((nx, ny, nz), _sub(fc, centre)) <= 0:
            problems.append(f"face {face}: normal points inward")
    return problems


def verify_claims(vertices, claims):
    """Numerically verify geometric claims; returns one result dict per claim."""
    results = []
    for claim in claims or []:
        ctype = claim.get("type")
        ok, actual = False, None
        try:
            if ctype == "distance":
                actual = _dist(vertices[claim["a"]], vertices[claim["b"]])
                ok = abs(actual - float(claim["expect"])) <= 1e-4
            elif ctype == "right_angle":
                va = _sub(vertices[claim["a"]], vertices[claim["vertex"]])
                vb = _sub(vertices[claim["b"]], vertices[claim["vertex"]])
                actual = _dot(va, vb)
                ok = abs(actual) <= 1e-6
            elif ctype == "parallel":
                u = _sub(vertices[claim["b"]], vertices[claim["a"]])
                v = _sub(vertices[claim["d"]], vertices[claim["c"]])
                actual = _norm(_cross(u, v))
                ok = actual <= 1e-6 * max(1.0, _norm(u) * _norm(v))
            elif ctype == "midpoint":
                mid = _centroid([vertices[claim["a"]], vertices[claim["b"]]])
                actual = _dist(mid, vertices[claim["point"]])
                ok = actual <= 1e-6
            else:
                results.append({"claim": claim, "ok": False, "actual": f"unknown claim type {ctype!r}"})
                continue
        except (KeyError, TypeError, ValueError) as exc:
            results.append({"claim": claim, "ok": False, "actual": f"bad claim: {exc}"})
            continue
        results.append({"claim": claim, "ok": bool(ok), "actual": actual})
    return results


# ---------- public entry point ----------

def build_solid(spec):
    """Build + validate a solid from a semantic spec.

    spec = {"kind": ..., "params": {...}, "claims": [...] (optional)}
    Returns render data plus the gate results. "ok" is True only when the
    structure is sound AND every claim holds — renderers must honour it.
    """
    kind = (spec or {}).get("kind")
    if kind not in _BUILDERS:
        return {"ok": False, "error": f"unknown solid kind: {kind!r}"}
    params = spec.get("params") or {}
    try:
        vertices, faces, aux, aux_edges = _BUILDERS[kind](**params)
    except TypeError as exc:
        return {"ok": False, "error": f"bad params for {kind}: {exc}"}

    problems = validate_solid(vertices, faces)
    claim_results = verify_claims(vertices, spec.get("claims"))
    ok = not problems and all(r["ok"] for r in claim_results)
    return {
        "ok": ok,
        "kind": kind,
        "params": params,
        "vertices": {k: list(v) for k, v in vertices.items()},
        "edges": [list(e) for e in _edges_from_faces(faces)],
        "faces": faces,
        "aux_points": aux,
        "aux_edges": aux_edges,
        "checks": {"structure": problems, "claims": claim_results},
    }


# ---------- preset library (figures from the grade-12 textbook) ----------

PRESETS = [
    {
        "id": "hop-oadb-cfme",
        "title": "Hình hộp OADB.CFME trong hệ Oxyz (Bài 7)",
        "spec": {
            "kind": "cuboid",
            "params": {"a": 3.0, "b": 4.0, "c": 2.5},
            "claims": [
                {"type": "right_angle", "a": "A", "vertex": "O", "b": "D"},
                {"type": "distance", "a": "O", "b": "B", "expect": 5.0},
            ],
        },
    },
    {
        "id": "lap-phuong",
        "title": "Hình lập phương ABCD.A'B'C'D'",
        "spec": {
            "kind": "cube",
            "params": {"s": 2.0},
            "claims": [
                {"type": "distance", "a": "A", "b": "C'", "expect": 3.46410161514},
            ],
        },
    },
    {
        "id": "chop-sabcd",
        "title": "Hình chóp S.ABCD, đáy hình vuông, SO vuông góc đáy",
        "spec": {
            "kind": "square_pyramid",
            "params": {"a": 4.0, "h": 3.0},
            "claims": [
                {"type": "midpoint", "point": "O", "a": "A", "b": "C"},
                {"type": "distance", "a": "S", "b": "O", "expect": 3.0},
            ],
        },
    },
    {
        "id": "lang-tru-tam-giac",
        "title": "Lăng trụ đứng ABC.A'B'C', đáy tam giác vuông tại A",
        "spec": {
            "kind": "triangular_prism",
            "params": {"a": 3.0, "b": 4.0, "h": 2.5},
            "claims": [
                {"type": "right_angle", "a": "B", "vertex": "A", "b": "C"},
                {"type": "distance", "a": "B", "b": "C", "expect": 5.0},
                {"type": "parallel", "a": "A", "b": "B", "c": "A'", "d": "B'"},
            ],
        },
    },
]
