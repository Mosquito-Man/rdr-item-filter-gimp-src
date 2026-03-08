import sys
import gi

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp, Gegl, GObject


PLUGIN_PROC = "python-fu-rdr-item-style-once"

DEFAULT_SETTINGS = {
    "saturation": 0.0,
    "black_level": 0.01,
    "exposure": 3.4,
    "mask_radius": 5.1209,
    "percent_black": 0.18,
    "shadow_x": 15.0,
    "shadow_y": 15.0,
    "shadow_radius": 6.2,
    "grow_radius": 4.0,
    "shadow_opacity": 0.52,
    "global_opacity": 1.0,
}

UI_PROPERTIES = [
    "saturation",
    "black-level",
    "exposure",
    "mask-radius",
    "percent-black",
    "shadow-x",
    "shadow-y",
    "shadow-radius",
    "grow-radius",
    "shadow-opacity",
    "global-opacity",
]


def _set_cfg_property(cfg, keys, value):
    key_list = keys if isinstance(keys, (list, tuple)) else [keys]
    for key in key_list:
        try:
            if hasattr(cfg, "find_property") and cfg.find_property(key) is None:
                continue
            cfg.set_property(key, value)
            return key
        except Exception:
            continue
    return None


def _set_cfg_property_with_values(cfg, keys, values):
    value_list = values if isinstance(values, (list, tuple)) else [values]
    for val in value_list:
        used = _set_cfg_property(cfg, keys, val)
        if used is not None:
            return used, val
    return None, None


def _apply_gegl(drawable, op_name, label, props):
    f = Gimp.DrawableFilter.new(drawable, op_name, label)
    cfg = f.get_config()
    for k, v in props.items():
        used = _set_cfg_property(cfg, k, v)
        if used is None:
            print(f"warn: {op_name} missing property {k}")
    f.update()
    drawable.append_filter(f)
    return f


def _edit_copy(one_drawable):
    try:
        return bool(Gimp.edit_copy([one_drawable]))
    except Exception:
        pass

    try:
        return bool(Gimp.edit_copy(one_drawable))
    except Exception:
        pass

    try:
        proc = Gimp.get_pdb().lookup_procedure("gimp-edit-copy")
        if proc:
            cfg = proc.create_config()
            for prop_name, prop_value in (("drawables", [one_drawable]), ("drawable", one_drawable)):
                try:
                    cfg.set_property(prop_name, prop_value)
                    break
                except Exception:
                    continue
            proc.run(cfg)
            return True
    except Exception:
        pass

    return False


def _edit_paste(target_drawable):
    for call in (
        lambda: Gimp.edit_paste([target_drawable], False),
        lambda: Gimp.edit_paste(target_drawable, False),
    ):
        try:
            result = call()
            if isinstance(result, (list, tuple)):
                return result[0] if result else None
            return result
        except Exception:
            continue

    try:
        proc = Gimp.get_pdb().lookup_procedure("gimp-edit-paste")
        if proc:
            cfg = proc.create_config()
            set_ok = False
            for prop_name, prop_value in (("drawables", [target_drawable]), ("drawable", target_drawable)):
                try:
                    cfg.set_property(prop_name, prop_value)
                    set_ok = True
                    break
                except Exception:
                    continue
            if not set_ok:
                return None

            for paste_prop in ("paste-into", "paste_into"):
                try:
                    cfg.set_property(paste_prop, False)
                    break
                except Exception:
                    continue

            result = proc.run(cfg)
            if isinstance(result, (list, tuple)):
                return result[1] if len(result) > 1 else (result[0] if result else None)
            return result
    except Exception:
        pass

    return None


def _anchor_floating(floating):
    if floating is None:
        return False

    try:
        floating.anchor()
        return True
    except Exception:
        pass

    try:
        Gimp.floating_sel_anchor(floating)
        return True
    except Exception:
        pass

    try:
        proc = Gimp.get_pdb().lookup_procedure("gimp-floating-sel-anchor")
        if proc:
            cfg = proc.create_config()
            for prop_name in ("floating-sel", "floating_sel", "drawable"):
                try:
                    cfg.set_property(prop_name, floating)
                    proc.run(cfg)
                    return True
                except Exception:
                    continue
    except Exception:
        pass

    return False


def _add_grayscale_copy_mask(target_drawable):
    for enum_name in ("GRAYSCALE_COPY", "GREYSCALE_COPY", "GRAY_COPY", "GREY_COPY"):
        enum_value = getattr(Gimp.AddMaskType, enum_name, None)
        if enum_value is None:
            continue
        try:
            mask = target_drawable.create_mask(enum_value)
            target_drawable.add_mask(mask)
            return True
        except Exception:
            continue

    mask = target_drawable.create_mask(Gimp.AddMaskType.WHITE)
    target_drawable.add_mask(mask)

    if not _edit_copy(target_drawable):
        return False

    floating = _edit_paste(mask)
    if floating is None:
        return False

    return _anchor_floating(floating)


def _run_pipeline(img, drawable, settings):
    print("starting")
    img.undo_group_start()
    try:
        sat_delta = float(settings["saturation"]) - 100.0
        drawable.hue_saturation(Gimp.HueRange.ALL, 0.0, 0.0, sat_delta, 0.0)
        print("step 1 ok")

        _apply_gegl(
            drawable,
            "gegl:exposure",
            "Exposure",
            {
                "black-level": settings["black_level"],
                "exposure": settings["exposure"],
            },
        )
        print("step 2 ok")

        _apply_gegl(
            drawable,
            "gegl:cartoon",
            "Cartoon",
            {
                "mask-radius": settings["mask_radius"],
                ("percent-black", "pct-black"): settings["percent_black"],
            },
        )
        print("step 3 ok")

        try:
            drawable.merge_filters()
        except Exception:
            pass
        try:
            drawable.update(0, 0, drawable.get_width(), drawable.get_height())
        except Exception:
            pass
        Gimp.displays_flush()

        if not _add_grayscale_copy_mask(drawable):
            raise RuntimeError("Failed to create/apply Grayscale Copy layer mask")
        print("step 4 ok")

        if not drawable.remove_mask(Gimp.MaskApplyMode.APPLY):
            raise RuntimeError("Failed to apply layer mask")
        print("step 5 ok")

        shadow_filter = Gimp.DrawableFilter.new(drawable, "gegl:dropshadow", "Drop Shadow")
        shadow_cfg = shadow_filter.get_config()

        for key, val in {
            "x": settings["shadow_x"],
            "y": settings["shadow_y"],
            "radius": settings["shadow_radius"],
            "grow-radius": settings["grow_radius"],
            "opacity": settings["shadow_opacity"],
            "color": Gegl.Color.new("black"),
        }.items():
            used = _set_cfg_property(shadow_cfg, key, val)
            if used is None:
                print(f"warn: gegl:dropshadow missing property {key}")

        used_shape, _ = _set_cfg_property_with_values(
            shadow_cfg,
            ("grow-shape", "grow_shape", "shape"),
            ("circle", 1),
        )
        if used_shape is None:
            print("warn: gegl:dropshadow could not set grow shape to circle")

        try:
            if hasattr(shadow_filter, "set_opacity"):
                shadow_filter.set_opacity(settings["global_opacity"])
        except Exception:
            print("warn: drawable filter global opacity setter unavailable")

        shadow_filter.update()
        drawable.append_filter(shadow_filter)
        print("step 6 ok")
    finally:
        img.undo_group_end()

    Gimp.displays_flush()
    print("done")


def _settings_dialog(initial_settings):
    gi.require_version("Gtk", "3.0")
    gi.require_version("GimpUi", "3.0")
    from gi.repository import Gtk, GimpUi

    settings = dict(initial_settings)

    GimpUi.init(PLUGIN_PROC)
    dialog = Gtk.Dialog(title="RDR Item Style", modal=True)
    dialog.add_button("_Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("_Apply", Gtk.ResponseType.OK)
    dialog.set_default_size(860, 620)

    content = dialog.get_content_area()
    grid = Gtk.Grid(column_spacing=10, row_spacing=8, margin=12)
    content.add(grid)

    def add_slider(row, key, label, mn, mx, step, digits=3):
        lbl = Gtk.Label(label=label, xalign=0)
        adj = Gtk.Adjustment(settings[key], mn, mx, step, step * 10, 0)
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        scale.set_digits(digits)
        scale.set_draw_value(True)
        scale.set_hexpand(True)

        def on_change(_scale):
            settings[key] = float(_scale.get_value())

        scale.connect("value-changed", on_change)
        grid.attach(lbl, 0, row, 1, 1)
        grid.attach(scale, 1, row, 1, 1)

    add_slider(0, "saturation", "Saturation (0-100)", 0.0, 100.0, 1.0, 0)
    add_slider(1, "black_level", "Black Point", 0.0, 0.2, 0.001)
    add_slider(2, "exposure", "Exposure", 0.1, 6.0, 0.05, 2)
    add_slider(3, "mask_radius", "Cartoon Radius", 1.0, 30.0, 0.1, 2)
    add_slider(4, "percent_black", "Cartoon Intensity", 0.0, 1.0, 0.01, 2)
    add_slider(5, "shadow_x", "Shadow X", -100.0, 100.0, 1.0, 0)
    add_slider(6, "shadow_y", "Shadow Y", -100.0, 100.0, 1.0, 0)
    add_slider(7, "shadow_radius", "Shadow Blur", 0.0, 30.0, 0.1, 2)
    add_slider(8, "grow_radius", "Shadow Grow", 0.0, 20.0, 0.1, 2)
    add_slider(9, "shadow_opacity", "Shadow Opacity", 0.0, 1.0, 0.01, 2)
    add_slider(10, "global_opacity", "Global Filter Opacity", 0.0, 1.0, 0.01, 2)

    dialog.show_all()
    ok = dialog.run() == Gtk.ResponseType.OK
    dialog.destroy()

    if ok:
        return settings
    return None


def run_pipeline():
    images = Gimp.get_images()
    if not images:
        raise RuntimeError("No image is open.")

    img = images[0]
    drawables = img.get_selected_drawables()
    if not drawables:
        raise RuntimeError("No drawable/layer is selected.")
    _run_pipeline(img, drawables[0], DEFAULT_SETTINGS)


class RdrItemStyleOncePlugin(Gimp.PlugIn):
    def do_query_procedures(self):
        return [PLUGIN_PROC]

    def do_create_procedure(self, name):
        if name != PLUGIN_PROC:
            return None

        procedure = Gimp.ImageProcedure.new(
            self,
            name,
            Gimp.PDBProcType.PLUGIN,
            self.run,
            None,
        )
        procedure.set_image_types("*")
        procedure.set_sensitivity_mask(Gimp.ProcedureSensitivityMask.DRAWABLE)
        procedure.set_menu_label("RDR Item Style")
        procedure.add_menu_path("<Image>/Filters/Artistic")
        procedure.set_documentation(
            "Apply RDR item style",
            "Runs the style with native GIMP sliders, then applies in fixed pipeline order.",
            name,
        )
        procedure.set_attribution("awesa", "awesa", "2026")

        procedure.add_double_argument(
            "saturation", "Saturation", "Output saturation level (0-100)",
            0.0, 100.0, DEFAULT_SETTINGS["saturation"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "black-level", "Black Point", "Exposure filter black level",
            0.0, 0.2, DEFAULT_SETTINGS["black_level"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "exposure", "Exposure", "Exposure amount",
            0.1, 6.0, DEFAULT_SETTINGS["exposure"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "mask-radius", "Cartoon Radius", "Cartoon mask radius",
            1.0, 30.0, DEFAULT_SETTINGS["mask_radius"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "percent-black", "Cartoon Intensity", "Cartoon black percentage",
            0.0, 1.0, DEFAULT_SETTINGS["percent_black"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "shadow-x", "Shadow X", "Drop shadow X offset",
            -100.0, 100.0, DEFAULT_SETTINGS["shadow_x"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "shadow-y", "Shadow Y", "Drop shadow Y offset",
            -100.0, 100.0, DEFAULT_SETTINGS["shadow_y"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "shadow-radius", "Shadow Blur", "Drop shadow blur radius",
            0.0, 30.0, DEFAULT_SETTINGS["shadow_radius"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "grow-radius", "Shadow Grow", "Drop shadow grow radius",
            0.0, 20.0, DEFAULT_SETTINGS["grow_radius"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "shadow-opacity", "Shadow Opacity", "Drop shadow opacity",
            0.0, 1.0, DEFAULT_SETTINGS["shadow_opacity"], GObject.ParamFlags.READWRITE,
        )
        procedure.add_double_argument(
            "global-opacity", "Global Filter Opacity", "Global filter stack opacity",
            0.0, 1.0, DEFAULT_SETTINGS["global_opacity"], GObject.ParamFlags.READWRITE,
        )
        return procedure

    def run(self, procedure, run_mode, image, drawables, config, data):
        try:
            if not drawables:
                raise RuntimeError("Select a layer first")

            settings = dict(DEFAULT_SETTINGS)
            if run_mode == Gimp.RunMode.INTERACTIVE:
                selected = _settings_dialog(settings)
                if selected is None:
                    return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, None)
                settings = selected

            _run_pipeline(image, drawables[0], settings)
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, None)
        except Exception as exc:
            print(f"{PLUGIN_PROC} error: {exc}")
            return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, None)


def _running_inside_python_console():
    argv0 = (sys.argv[0] if sys.argv else "").lower()
    return "python-console.py" in argv0


def main(argv=None):
    if _running_inside_python_console():
        print("rdr_item_img_once.py loaded in Python Console (registration skipped).")
        return
    Gimp.main(RdrItemStyleOncePlugin.__gtype__, argv or sys.argv)


if __name__ == "__main__":
    main()