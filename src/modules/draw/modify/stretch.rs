// Stretch tool — ribbon definition + interactive command.
//
// Command:  STRETCH (SS)
//   Workflow:
//     1. Pick first corner of the crossing window (right-to-left = crossing).
//     2. Pick second corner.
//     3. Pick base point.
//     4. Pick new point → stretches only vertices inside the crossing window.
//
//   Entity behaviour:
//     Line        : move start if inside, move end if inside, move both if both inside.
//     LwPolyline  : move each vertex independently.
//     Polyline/P2D: move each vertex independently.
//     Arc / Circle: move the whole entity if its center is inside the window.
//     Insert      : move the whole entity if its insertion point is inside.
//     All others  : move the whole entity if any point is inside.

use acadrust::Handle;
use glam::DVec3;

use crate::command::{CadCommand, CmdResult};
use crate::modules::{IconKind, ModuleEvent, ToolDef};
use crate::scene::model::wire_model::WireModel;

// ── Ribbon definition ──────────────────────────────────────────────────────

pub fn tool() -> ToolDef {
    ToolDef {
        id: "STRETCH",
        label: "Stretch",
        icon: IconKind::Svg(include_bytes!("../../../../assets/icons/stretch.svg")),
        event: ModuleEvent::Command("STRETCH".to_string()),
    }
}

// ── Command implementation ─────────────────────────────────────────────────

enum Step {
    /// Waiting for the first crossing-window corner.
    WindowCorner1,
    /// Waiting for the second corner; `c1` is the first corner.
    WindowCorner2(DVec3),
    /// Crossing window defined; waiting for base point.
    Base { win_min: DVec3, win_max: DVec3 },
    /// Waiting for target point.
    Target {
        win_min: DVec3,
        win_max: DVec3,
        base: DVec3,
    },
}

pub struct StretchCommand {
    handles: Vec<Handle>,
    wire_models: Vec<WireModel>,
    step: Step,
}

impl StretchCommand {
    pub fn new(handles: Vec<Handle>, wire_models: Vec<WireModel>) -> Self {
        Self {
            handles,
            wire_models,
            step: Step::WindowCorner1,
        }
    }
}

impl CadCommand for StretchCommand {
    fn name(&self) -> &'static str {
        "STRETCH"
    }

    fn prompt(&self) -> String {
        match &self.step {
            Step::WindowCorner1 => format!(
                "STRETCH  Specify first corner of crossing window  [{} objects]:",
                self.handles.len()
            ),
            Step::WindowCorner2(_) => "STRETCH  Specify opposite corner:".into(),
            Step::Base { .. } => "STRETCH  Specify base point:".into(),
            Step::Target { base, .. } => format!(
                "STRETCH  Specify new point  [base {:.3},{:.3}]:",
                base.x, base.z
            ),
        }
    }

    fn on_point(&mut self, pt: DVec3) -> CmdResult {
        match &self.step {
            Step::WindowCorner1 => {
                self.step = Step::WindowCorner2(pt);
                CmdResult::NeedPoint
            }
            Step::WindowCorner2(c1) => {
                let win_min = c1.min(pt);
                let win_max = c1.max(pt);
                self.step = Step::Base { win_min, win_max };
                CmdResult::NeedPoint
            }
            Step::Base { win_min, win_max } => {
                let (wmin, wmax) = (*win_min, *win_max);
                self.step = Step::Target {
                    win_min: wmin,
                    win_max: wmax,
                    base: pt,
                };
                CmdResult::NeedPoint
            }
            Step::Target {
                win_min,
                win_max,
                base,
            } => {
                let delta = pt - *base;
                CmdResult::StretchEntities {
                    handles: self.handles.clone(),
                    win_min: *win_min,
                    win_max: *win_max,
                    delta,
                }
            }
        }
    }

    fn on_enter(&mut self) -> CmdResult {
        CmdResult::Cancel
    }
    fn on_escape(&mut self) -> CmdResult {
        CmdResult::Cancel
    }

    fn window_corner_pick(&self) -> bool {
        // The two crossing-window corners are free points; Ortho/Polar must not
        // pin the opposite corner to an axis or the window becomes a line (#291).
        matches!(self.step, Step::WindowCorner1 | Step::WindowCorner2(_))
    }

    fn window_first_corner(&self) -> Option<DVec3> {
        // Expose the first corner so the host draws a filled crossing marquee to
        // the cursor, matching a normal box selection instead of a bare outline.
        match &self.step {
            Step::WindowCorner2(c1) => Some(*c1),
            _ => None,
        }
    }

    fn on_preview_wires(&mut self, pt: DVec3) -> Vec<WireModel> {
        match &self.step {
            // The crossing-window rectangle is drawn as a filled selection
            // marquee by the host (via window_first_corner) so it matches a
            // normal box selection — nothing to draw here. (#291)
            Step::WindowCorner2(_) => vec![],
            Step::Target {
                win_min,
                win_max,
                base,
            } => {
                let delta = pt - *base;
                // Live ghost: vertices inside the crossing window follow the
                // cursor, the rest stay anchored. This is the preview/GPU path,
                // so downcast to f32 only at the WireModel boundary.
                let mut out: Vec<WireModel> = self
                    .wire_models
                    .iter()
                    .map(|w| w.stretched((*win_min).as_vec3(), (*win_max).as_vec3(), delta.as_vec3()))
                    .collect();
                out.push(WireModel::solid(
                    "rubber_band".into(),
                    vec![
                        [base.x as f32, base.y as f32, base.z as f32],
                        [pt.x as f32, pt.y as f32, pt.z as f32],
                    ],
                    WireModel::CYAN,
                    false,
                ));
                out
            }
            _ => vec![],
        }
    }
}
