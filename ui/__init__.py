import shutil
import sys
import threading
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel

from ..blender.importer import import_asset
from ..blender.region import ALL, KINDS, import_region
from ..divinity2 import catalog, docs, region
from dv2lib import locate, unpack

PACKAGE = __package__.rpartition(".")[0]


def _game_root(context) -> str:
    prefs = context.preferences.addons[PACKAGE].preferences
    if prefs.game_root and docs.ROOTS[:1] != [Path(prefs.game_root)]:
        docs.begin(prefs.game_root)
    return prefs.game_root


def _cache() -> str:
    # bpy.utils.extension_path_user bpy
    return bpy.utils.extension_path_user(PACKAGE, path="texture-cache", create=True)


UNPACKED_BYTES = 7_400_000_000

_unpacking = {"thread": None, "done": 0, "total": 0, "stop": False, "said": ""}


class _Stopped(Exception):
    pass


def _forget_reads() -> None:
    for name, module in list(sys.modules.items()):
        if name.startswith(PACKAGE + ".divinity2."):
            for value in list(vars(module).values()):
                if callable(getattr(value, "cache_clear", None)):
                    value.cache_clear()


def _watch_unpack():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "PREFERENCES":
                area.tag_redraw()
    if _unpacking["thread"] is not None and _unpacking["thread"].is_alive():
        return 0.5
    _unpacking["thread"] = None
    _forget_reads()
    return None


class DV2_OT_unpack(Operator):
    bl_idname = "divinity2.unpack"
    bl_label = "Unpack the game"

    def execute(self, context):
        if _unpacking["thread"] is not None:
            _unpacking["stop"] = True
            return {"FINISHED"}
        prefs = context.preferences.addons[PACKAGE].preferences
        game = prefs.install or locate.find_game()
        packed = locate.packed_of(game) if game else None
        if packed is None:
            self.report({"ERROR"}, f"No Divinity II archives in {game}" if game else
                        "Set the Divinity II install: the folder holding Data and bin")
            return {"CANCELLED"}
        if not prefs.game_root:
            self.report({"ERROR"}, "Set the game folder to unpack into")
            return {"CANCELLED"}
        out = Path(prefs.game_root)
        out.mkdir(parents=True, exist_ok=True)
        if any(out.iterdir()) and not (out / "unpack.json").is_file():
            self.report({"ERROR"}, f"{out} is not empty: choose an empty folder")
            return {"CANCELLED"}
        if shutil.disk_usage(out).free < UNPACKED_BYTES:
            self.report({"ERROR"}, f"Unpacking needs about 7 GB free in {out}")
            return {"CANCELLED"}

        def progress(done, total):
            _unpacking["done"], _unpacking["total"] = done, total
            if _unpacking["stop"]:
                raise _Stopped

        def work():
            try:
                meta = unpack.unpack(packed, out, progress)
                _unpacking["said"] = f"Unpacked {meta['files']:,} files and {meta['documents']:,} documents"
            except _Stopped:
                _unpacking["said"] = (f"Stopped at {_unpacking['done']:,} of {_unpacking['total']:,} "
                                      "files: unpack again to finish")
            except Exception as exc:
                _unpacking["said"] = f"Unpacking failed: {exc}"

        _unpacking.update(done=0, total=0, stop=False, said="")
        _unpacking["thread"] = threading.Thread(target=work, daemon=True)
        _unpacking["thread"].start()
        bpy.app.timers.register(_watch_unpack, first_interval=0.5)
        return {"FINISHED"}


class DV2_AddonPreferences(AddonPreferences):
    bl_idname = PACKAGE

    install: StringProperty(
        name="Divinity II install",
        description="The Developer's Cut as installed, the folder holding Data and bin. "
                    "Empty: every Steam library is searched",
        subtype="DIR_PATH",
        default="",
    )

    game_root: StringProperty(
        name="Game folder",
        description="An empty folder the game is unpacked into, and read from",
        subtype="DIR_PATH",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "install")
        layout.prop(self, "game_root")
        running = _unpacking["thread"] is not None
        row = layout.row()
        row.operator(DV2_OT_unpack.bl_idname, text="Stop unpacking" if running else "Unpack the game",
                     icon="CANCEL" if running else "PACKAGE")
        if running:
            total = _unpacking["total"] or 1
            row.label(text=f"{_unpacking['done']:,} of {_unpacking['total']:,} files "
                           f"({100 * _unpacking['done'] // total} %)")
        elif _unpacking["said"]:
            row.label(text=_unpacking["said"])
        elif self.game_root and not catalog.looks_like_game(self.game_root):
            row.label(text="Not unpacked yet", icon="ERROR")
        elif self.game_root and not (Path(self.game_root) / "docs").is_dir():
            row.label(text="No documents: regions need them, unpack again", icon="ERROR")


def _asset_items(self, context):
    root = _game_root(context)
    if not root:
        return [("", "Unpack the game in Preferences", "")]
    found = catalog.search(root, self.search)
    if not found:
        return [("", "Nothing matches", "")]
    return [(str(a.path), a.name, a.kind) for a in found]


class DV2_OT_import_asset(Operator):
    bl_idname = "divinity2.import_asset"
    bl_label = "Divinity II asset"
    bl_options = {"REGISTER", "UNDO"}

    search: StringProperty(name="Name", default="")
    choice: EnumProperty(name="Asset", items=_asset_items)

    def invoke(self, context, event):
        if not _game_root(context):
            self.report({"ERROR"}, "Unpack the game in the add-on's Preferences")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "search")
        layout.prop(self, "choice")

    def _resolve(self, context) -> str | None:
        if self.choice:
            return self.choice
        root = _game_root(context)
        found = catalog.search(root, self.search) if root else []
        exact = [a for a in found if a.name.lower() == self.search.lower()]
        if exact:
            return str(exact[0].path)
        if len(found) == 1:
            return str(found[0].path)
        if found:
            self.report(
                {"ERROR"}, f"{len(found)} assets match '{self.search}' -- pick one"
            )
        else:
            self.report({"ERROR"}, f"Nothing matches '{self.search}'")
        return None

    def execute(self, context):
        chosen = self._resolve(context)
        if chosen is None:
            return {"CANCELLED"}

        result = import_asset(chosen, _game_root(context), cache=_cache())
        self.report(
            {"INFO"},
            f"{len(result.objects)} objects, {result.bones} bones, "
            f"{result.skinned} skinned, {result.clips} clips",
        )
        return {"FINISHED"}


def _region_items(self, context):
    root = _game_root(context)
    found = region.regions(root) if root else []
    return [(n, n, "") for n in found] or [("", "No regions: unpack the game, see Preferences", "")]


def _sub_items(self, context):
    root = _game_root(context)
    found = region.subregions(root, self.region_name) if root and self.region_name else []
    items = [(n, n, "") for n in found] or [("Main", "Main", "")]
    if len(found) > 1:
        items.append((ALL, f"All {len(found)}",
                      "Each has its own origin, so all but the first arrive "
                      "switched off"))
    return items


# bpy.props.EnumProperty bpy
GAME_TIME = "<game>"


def _time_items(self, context):
    root = _game_root(context)
    listed = (region.time_settings(root, self.region_name, self.sub)
              if root and self.region_name and self.sub != ALL else [])
    _time_items.keep = [(GAME_TIME, "As the game does", "`CGameLogic_SubRegion::Load`'s choice")] \
        + [(t, t, "A time setting this sub-region lists") for t in listed]
    return _time_items.keep


class DV2_OT_import_region(Operator):
    bl_idname = "divinity2.import_region"
    bl_label = "Divinity II region"
    bl_options = {"REGISTER", "UNDO"}

    region_name: EnumProperty(name="Region", items=_region_items)
    sub: EnumProperty(name="Sub-region", items=_sub_items)
    time: EnumProperty(name="Time of day", items=_time_items)
    terrain: BoolProperty(name="Ground", default=True)
    scenery: BoolProperty(name="Scenery", default=True)
    item: BoolProperty(name="Items", default=True)
    character: BoolProperty(name="Characters", default=True)
    light: BoolProperty(name="Lights", default=True)
    tree: BoolProperty(name="Trees", default=True)
    trigger: BoolProperty(name="Triggers", default=False)
    vegetation: BoolProperty(name="Grass", default=False)

    def invoke(self, context, event):
        if not _game_root(context):
            self.report({"ERROR"}, "Unpack the game in the add-on's Preferences")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "region_name")
        layout.prop(self, "sub")
        layout.prop(self, "time")
        grid = layout.grid_flow(columns=2, even_columns=True)
        for kind in KINDS:
            grid.prop(self, kind)

    def execute(self, context):
        chosen = tuple(k for k in KINDS if getattr(self, k))
        built = import_region(
            _game_root(context), self.region_name, self.sub,
            "" if self.time == GAME_TIME else self.time, chosen, cache=_cache()
        )
        for failure in built.failed[:5]:
            self.report({"WARNING"}, failure)
        parts = ", ".join(f"{v} {k}" for k, v in built.counts.items())
        self.report(
            {"INFO"},
            f"{self.region_name}/{self.sub}: {parts or 'nothing'} "
            f"from {built.models} models, {built.unresolved} unresolved",
        )
        return {"FINISHED"}


class DV2_PT_panel(Panel):
    bl_label = "Divinity II"
    bl_idname = "DV2_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Divinity II"

    def draw(self, context):
        layout = self.layout
        if not _game_root(context):
            layout.label(text="Unpack the game in Preferences", icon="ERROR")
            return
        layout.operator(DV2_OT_import_asset.bl_idname, icon="OUTLINER_OB_ARMATURE")
        layout.operator(DV2_OT_import_region.bl_idname, icon="WORLD")


def _menu(self, context):
    self.layout.operator(DV2_OT_import_asset.bl_idname, text="Divinity II asset")
    self.layout.operator(DV2_OT_import_region.bl_idname, text="Divinity II region")


_classes = (DV2_OT_unpack, DV2_AddonPreferences, DV2_OT_import_asset,
            DV2_OT_import_region, DV2_PT_panel)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(_menu)


def unregister():
    _unpacking["stop"] = True
    if bpy.app.timers.is_registered(_watch_unpack):
        bpy.app.timers.unregister(_watch_unpack)
    bpy.types.TOPBAR_MT_file_import.remove(_menu)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
