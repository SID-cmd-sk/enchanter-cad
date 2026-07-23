"""
posts/__init__.py
Pluggable G-code POST-PROCESSOR system for PyCAD.

A post is just a Python FILE in this folder (posts/).  One machine = one .py
file.  PyCAD discovers every .py post automatically - drop in 1 file, you get
1 post; drop in 20 files, you get 20 posts.  No central registry, no JSON,
nothing to recompile.  Edit a .py file and restart PyCAD (or click refresh in
the Post menu) and the new machine appears.

This matches the "single .exe but editable without rebuilding" goal: because
posts are plain .py modules loaded at runtime, you can tweak any machine's
G-code output on the installed app without touching the compiled binary.

How to write your own post (see fanuc.py for a complete example):

    from posts.base import BasePost

    class Post(BasePost):
        name        = "My Mill"                 # shown in the post dropdown
        description = "Short note about the machine"
        # variables: default values the post can use in its templates
        variables = {"SAFE_Z": 10.0, "PARK_X": 0.0, "PARK_Y": 0.0}
        # options: simple toggles the processor reads
        options = {"absolute": True, "metric": True, "use_i_j": True,
                   "arc_clockwise": "G02", "arc_ccw": "G03",
                   "comment_paren": True, "use_wcs": True}
        # templates: Python str.format() strings. Placeholders:
        #   {x} {y} {z} {f} {i} {j} {r} {tool} {rpm} {wcs}
        #   {p} {name} {text} {code} {dnum} {var:SAFE_Z}
        templates = {
            "program_start": "%\n(--- {name} ---)\nG21 G90 G17 G94\n",
            "wcs":          "{wcs}\n",
            ...
        }

The processor (process_events) walks the toolpath events produced by gcode.py
and fills in the templates.  You can also OVERRIDE methods on the post (e.g.
def program_start(self, ctx) -> str) for full programmatic control.
"""

import os
import importlib.util
import sys


# Folder that holds the per-machine post .py files (this folder).
POSTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_post_module(path):
    """Import a .py file by path and return its Post class (subclass of
    BasePost), or None if it doesn't define one."""
    from posts.base import BasePost
    modname = "_pycad_post_" + os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        # a broken post must never crash the app - just skip it
        return None
    post_cls = getattr(mod, "Post", None)
    if post_cls is None or not isinstance(post_cls, type) \
       or not issubclass(post_cls, BasePost):
        return None
    return post_cls


def discover_posts(posts_dir=POSTS_DIR):
    """Return a list of Post INSTANCES, one per .py file found in posts_dir.

    Any .py file in this folder that defines a `Post(BasePost)` class is
    picked up.  Order is alphabetical by filename.  The special module
    `base.py` and this `__init__.py` are ignored.
    """
    posts = []
    if not os.path.isdir(posts_dir):
        return posts
    for fn in sorted(os.listdir(posts_dir)):
        if not fn.lower().endswith(".py"):
            continue
        if fn.lower() in ("__init__.py", "base.py"):
            continue
        path = os.path.join(posts_dir, fn)
        try:
            cls = _load_post_module(path)
        except Exception:
            cls = None
        if cls is None:
            continue
        try:
            posts.append(cls())
        except Exception:
            continue
    return posts


def get_post(name, posts_dir=POSTS_DIR):
    for p in discover_posts(posts_dir):
        if p.name == name:
            return p
    return None


def list_post_names(posts_dir=POSTS_DIR):
    return [p.name for p in discover_posts(posts_dir)]


# ---------------------------------------------------------------------------
# Compatibility shim (the old posts.py API, kept so gcode_dialog.py / main.py
# keep working).  A Post is any BasePost instance; the editor builds one from
# a dict and serializes it to its own .py file.
# ---------------------------------------------------------------------------
from posts.base import BasePost  # noqa: E402
DEFAULT_POSTS_DIR = POSTS_DIR


class Post(BasePost):
    """A post built from a plain dict (e.g. the editor UI) and serializable to
    its own .py file in posts/.  Inherits all template-processing logic."""

    def __init__(self, data=None):
        data = data or {}
        self.name = data.get("name", "Unnamed Post")
        self.description = data.get("description", "")
        self.variables = dict(data.get("variables", {}))
        self.options = dict(BasePost.options)
        self.options.update(data.get("options", {}))
        self.templates = dict(data.get("templates", {}))

    def save_to_folder(self, folder):
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.name)
        safe = safe or "my_post"
        path = os.path.join(folder, safe + ".py")
        with open(path, "w", encoding="utf-8") as f:
            f.write('"""Auto-generated PyCAD post.  Edit freely."""\n')
            f.write("from posts.base import BasePost\n\n\n")
            f.write("class Post(BasePost):\n")
            f.write(f"    name = {self.name!r}\n")
            f.write(f"    description = {self.description!r}\n\n")
            f.write(f"    variables = {self.variables!r}\n\n")
            f.write(f"    options = {self.options!r}\n\n")
            f.write("    templates = {\n")
            for k, v in self.templates.items():
                f.write(f"        {k!r}: {v!r},\n")
            f.write("    }\n")
        return path


class PostManager:
    """Thin wrapper over posts/ discovery so old code keeps working."""

    def __init__(self, posts_dir=DEFAULT_POSTS_DIR):
        self.posts_dir = posts_dir

    def list_posts(self):
        return discover_posts(self.posts_dir)

    def get_post(self, name):
        return get_post(name, self.posts_dir)

    def list_names(self):
        return list_post_names(self.posts_dir)

    def save_user_post(self, post):
        return post.save_to_folder(self.posts_dir) if hasattr(post, "save_to_folder") else self.posts_dir

    def delete_user_post(self, name):
        return False


def process_events(events, post, params):
    """events: toolpath events from gcode.emit_path_to_events.
    post: a BasePost instance.  params: GCodeParams (supplies defaults)."""
    name = getattr(params, "jobname", "PyCAD") or "PyCAD"
    ctx = {
        "name": name,
        "wcs": getattr(params, "wcs", "G54"),
        "plungef": getattr(params, "plungef", 200.0),
    }
    return post.process(events, ctx)
