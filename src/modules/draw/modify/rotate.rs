// Rotate tool — ribbon definition + interactive command.
//
// Command:  ROTATE (RO)
//   Requires at least one entity selected before starting.
//   Step 1: pick rotation center
//   Step 2: pick reference point (defines the 0° direction)
//   Step 3: pick destination point → rotates by (dest_angle - ref_angle)

use acadrust::Handle;
use glam::DVec3;

use crate::command::{CadCommand, CmdResult, DynField, EntityTransform};
use crate::modules::draw::defaults;
use crate::modules::{IconKind, ModuleEvent, ToolDef};
use crate::scene::model::wire_model::WireModel;

// ── Ribbon definition ──────────────────────────────────────────────────────

pub fn tool() -> ToolDef {
    ToolDef {
        id: "ROTATE",
        label: "Rotate",
        icon: IconKind::Svg(include_bytes!("../../../../assets/icons/rotate.svg")),
        event: ModuleEvent::Command("ROTATE".to_string()),
    }
}

// ── Command implementation ─────────────────────────────────────────────────

enum Step {
    Center,
    RefPoint { center: DVec3 },
    Angle { center: DVec3, ref_angle: f64 },
}

pub struct RotateCommand {
    handles: Vec<Handle>,
    wire_models: Vec<WireModel>,
    step: Step,
    default_angle: f64, // degrees
}

impl RotateCommand {
    pub fn new(handles: Vec<Handle>, wire_models: Vec<WireModel>) -> Self {
        Self {
            handles,
            wire_models,
            step: Step::Center,
            default_angle: defaults::get_rotate_angle(),
        }
    }
}

impl CadCommand for RotateCommand {
    fn name(&self) -> &'static str {
        "ROTATE"
    }

    fn prompt(&self) -> String {
        match &self.step {
            Step::Center => format!(
                "ROTATE  Specify rotation center  [{} objects]:",
                self.handles.len()
            ),
            Step::RefPoint { .. } => {
                "ROTATE  Specify reference point  (or skip: type angle directly):".into()
            }
            Step::Angle { ref_angle, .. } => format!(
                "ROTATE  Specify destination or type angle in degrees  <{:.4}>  [ref={:.1}°]:",
                self.default_angle,
                ref_angle.to_degrees()
            ),
        }
    }

    fn on_point(&mut self, pt: DVec3) -> CmdResult {
        match &self.step {
            Step::Center => {
                self.step = Step::RefPoint { center: pt };
                CmdResult::NeedPoint
            }
            Step::RefPoint { center } => {
                let center = *center;
                let ref_angle = (pt.y - center.y).atan2(pt.x - center.x);
                self.step = Step::Angle { center, ref_angle };
                CmdResult::NeedPoint
            }
            Step::Angle { center, ref_angle } => {
                let center = *center;
                let ref_angle = *ref_angle;
                let dest_angle = (pt.y - center.y).atan2(pt.x - center.x);
                let delta = dest_angle - ref_angle;
                defaults::set_rotate_angle(delta.to_degrees());
                self.default_angle = delta.to_degrees();
                CmdResult::TransformSelected(
                    self.handles.clone(),
                    EntityTransform::Rotate {
                        center,
                        angle_rad: delta,
                    },
                )
            }
        }
    }

    fn on_enter(&mut self) -> CmdResult {
        // At Angle step: Enter uses the stored default angle.
        if let Step::Angle { center, .. } = &self.step {
            let center = *center;
            let angle_rad = self.default_angle.to_radians();
            return CmdResult::TransformSelected(
                self.handles.clone(),
                EntityTransform::Rotate { center, angle_rad },
            );
        }
        CmdResult::Cancel
    }
    fn on_escape(&mut self) -> CmdResult {
        CmdResult::Cancel
    }

    fn on_text_input(&mut self, text: &str) -> Option<CmdResult> {
        // A typed angle rotates directly about the centre. Accept it at the
        // reference-point step too (the prompt offers "skip: type angle
        // directly") — otherwise typing the angle there did nothing and the
        // command cancelled on the next Enter, so the objects never rotated.
        let center = match &self.step {
            Step::RefPoint { center } => *center,
            Step::Angle { center, .. } => *center,
            Step::Center => return None,
        };
        // The value already carries the correct sign (the dynamic-input
        // layer applies the cursor's side for a bare magnitude).
        let deg: f64 = text.trim().replace(',', ".").parse().ok()?;
        defaults::set_rotate_angle(deg);
        Some(CmdResult::TransformSelected(
            self.handles.clone(),
            EntityTransform::Rotate {
                center,
                angle_rad: deg.to_radians(),
            },
        ))
    }

    fn on_preview_wires(&mut self, pt: DVec3) -> Vec<WireModel> {
        let (center, ref_angle) = match &self.step {
            Step::Angle { center, ref_angle } => (*center, *ref_angle),
            Step::RefPoint { center } => {
                // Show a reference line from center to cursor only.
                return vec![WireModel::solid(
                    "rubber_band".into(),
                    vec![
                        [center.x as f32, center.y as f32, center.z as f32],
                        [pt.x as f32, pt.y as f32, pt.z as f32],
                    ],
                    WireModel::CYAN,
                    false,
                )];
            }
            _ => return vec![],
        };
        let dest_angle = (pt.y - center.y).atan2(pt.x - center.x);
        let angle_rad = dest_angle - ref_angle;
        // Track the live SIGNED rotation (relative to the reference) so that
        // committing with Enter rotates the way the cursor is dragging — the
        // dynamic-input box shows the unsigned magnitude, but the committed
        // value must keep its direction (clockwise = negative).
        self.default_angle = angle_rad.to_degrees();
        // Object ghosts rotated to the new angle. The rotation sweep arc is
        // drawn by the dynamic-input overlay (polar guide), not here.
        self.wire_models
            .iter()
            .map(|w| w.rotated(center.as_vec3(), angle_rad as f32))
            .collect()
    }

    fn dyn_field(&self) -> DynField {
        match self.step {
            Step::Angle { .. } => DynField::Angle,
            _ => DynField::Point,
        }
    }

    fn dyn_spec(&self) -> Option<crate::command::DynSpec> {
        use crate::command::{DynAnchor, DynFieldSpec, DynGuide, DynRole, DynSpec};
        // Rotation angle is measured about the CENTRE, swept from the reference
        // direction. The polar guide arc is anchored at the centre and starts
        // at the reference (via ref_point), with the value box centred on it.
        if let Step::Angle { center, ref_angle } = self.step {
            let ref_dir = DVec3::new(center.x + ref_angle.cos(), center.y + ref_angle.sin(), center.z);
            Some(DynSpec {
                anchor: DynAnchor::Point(center),
                fields: vec![DynFieldSpec::new(DynRole::Angle)],
                guide: DynGuide::Polar,
                ref_point: Some(ref_dir),
            })
        } else {
            None
        }
    }

    fn dyn_commit_as_text(&self) -> bool {
        matches!(self.step, Step::Angle { .. })
    }

    fn dyn_live_value(&self, cursor: DVec3) -> Option<f64> {
        // The rotation amount = cursor direction from the centre minus the
        // reference angle, so the box reads the actual rotation.
        if let Step::Angle { center, ref_angle } = &self.step {
            let dest = (cursor.y - center.y).atan2(cursor.x - center.x);
            Some(crate::command::dyn_display_angle_deg((dest - ref_angle) as f32) as f64)
        } else {
            None
        }
    }
}
