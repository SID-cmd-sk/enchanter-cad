# Open CAD Studio — Status Bar Items

Tracks the status-bar toggle pills, the customization menu, and which
items are implemented, deferred, or out of scope.

The customization menu (the `≡` handle at the bar's far right) lists every
pill with a check mark; toggling a row shows/hides that pill and the choice
persists across sessions.

- Pill definitions & visibility: [`src/ui/statusbar_config.rs`](src/ui/statusbar_config.rs)
- Bar layout & pills: [`src/ui/statusbar.rs`](src/ui/statusbar.rs)
- Customization menu: [`src/ui/statusbar_menu.rs`](src/ui/statusbar_menu.rs)

## Implemented

| Item | Pill | Source |
|------|------|--------|
| Coordinates (live cursor X,Y,Z) | `Coords` | [statusbar.rs](src/ui/statusbar.rs) `format_coords` |
| Snap Mode | `SNAP` | pre-existing |
| Grid | `GRID` | pre-existing |
| Ortho Mode | `ORTHO` | pre-existing |
| Polar Tracking | `POLAR` | pre-existing |
| Dynamic Input | `DYN` | pre-existing |
| Object Snap Tracking | `OTRACK` | pre-existing |
| 2D Object Snap | `OSNAP` | pre-existing |
| Lineweight display | `LWT` | pre-existing |
| Model / Paper space | `Space` | pre-existing |
| Annotation scale | `Scale` | [scale_popup.rs](src/ui/scale_popup.rs) |
| Drawing units (INSUNITS) | `Units` | [units_popup.rs](src/ui/units_popup.rs) |
| Transparency display | `TPY` | [uniforms.rs](src/scene/pipeline/uniforms.rs) + [wire.wgsl](src/shaders/wire.wgsl) |
| Isolate / Hide objects | `Isolate` | [isolate_popup.rs](src/ui/isolate_popup.rs); commands `ISOLATEOBJECTS` / `HIDEOBJECTS` / `UNISOLATEOBJECTS` |
| Quick Properties | `QP` | [properties.rs](src/ui/properties.rs) `quick_view` |
| Selection Filtering | `FILTER` | [selection_filter_popup.rs](src/ui/selection_filter_popup.rs) |
| Selection Cycling | `SC` | [cycle_popup.rs](src/ui/cycle_popup.rs) — pick list + hover highlight |
| Clean Screen | `CleanScreen` | hides ribbon + side panels |
| Viewport count (app-specific) | `Vp` | — |

## Remaining — annotative engine

These are not single pills; they need a real annotative-objects subsystem:
a per-entity annotative flag, the list of scales each object supports, and a
**separate representation (size / position) per scale**, with render-time
selection by the current annotation scale.

| Item | Needs |
|------|-------|
| Annotation Visibility | hide annotative objects whose scale list omits the current scale |
| AutoScale | add the current scale's representation automatically when the scale changes |
| Annotation Monitor | warn on annotative inconsistencies |

The pieces that exist today (`annotation_scale`, dimstyle / multileader
annotative flags) do not yet include the per-scale representation system.
Best tackled as a separate, staged effort (start with Visibility).

## Dropped — no fit in this architecture

| Item | Why |
|------|-----|
| Lock UI | panels are separate OS windows; there is no dock layout to lock |
| Graphics Performance | a GPU-tuning dialog with no meaningful equivalent here |

## Out of scope — large standalone engines

Each is a product-level subsystem, not a status pill:

- Infer Constraints (parametric constraint solver)
- Isometric Drafting (isometric drawing mode)
- 3D Object Snap
- Dynamic UCS (auto-align UCS to the face under the cursor)
- Gizmo (3D move/rotate manipulator)
- Workspace Switching (multiple ribbon workspaces)
