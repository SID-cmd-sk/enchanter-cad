// Hatch/Gradient/Boundary commands — OpenCADStudio Home > Draw > Hatch dropdown.
//
// Commands:
//   HATCH    — ANSI31: 45° hatch lines (pick inside or type S for manual)
//   GRADIENT — Linear gradient fill (pick inside or type S for manual)
//   BOUNDARY — Traces the enclosing boundary as a closed LwPolyline
//
// Primary workflow (matches OpenCADStudio):
//   Click a point INSIDE a closed region → boundary auto-detected.
//   Type "S" to switch to manual vertex-picking mode (HATCH/GRADIENT only).

use crate::command::{CadCommand, CmdResult};
use crate::modules::IconKind;
use crate::scene::model::hatch_model::{HatchModel, HatchPattern, PatFamily};
use crate::scene::model::wire_model::WireModel;
use glam::DVec3;

// ── Icons ──────────────────────────────────────────────────────────────────

const ICON_HATCH: IconKind = IconKind::Svg(include_bytes!(
    "../../../../assets/icons/hatch/hatch_lines.svg"
));
const ICON_GRADIENT: IconKind = IconKind::Svg(include_bytes!(
    "../../../../assets/icons/hatch/hatch_gradient.svg"
));
const ICON_BOUNDARY: IconKind = IconKind::Svg(include_bytes!(
    "../../../../assets/icons/hatch/hatch_boundary.svg"
));

// ── Dropdown metadata ──────────────────────────────────────────────────────

pub const DROPDOWN_ID: &str = "HATCH";
pub const ICON: IconKind = ICON_HATCH;

pub const DROPDOWN_ITEMS: &[(&str, &str, IconKind)] = &[
    ("HATCH", "Hatch", ICON_HATCH),
    ("GRADIENT", "Gradient", ICON_GRADIENT),
    ("BOUNDARY", "Boundary", ICON_BOUNDARY),
];

// ── Shared mode ────────────────────────────────────────────────────────────

enum Mode {
    /// Primary: click inside a closed shape → boundary auto-detected.
    PickInside,
    /// Fallback: user manually picks polygon vertices (type "S" to enter).
    Manual,
}

// ── CPU point-in-polygon (ray casting) ────────────────────────────────────

fn point_in_polygon(p: [f32; 2], poly: &[[f32; 2]]) -> bool {
    let n = poly.len();
    if n < 3 {
        return false;
    }
    let mut inside = false;
    let mut j = n - 1;
    for i in 0..n {
        let vi = poly[i];
        let vj = poly[j];
        if (vi[1] > p[1]) != (vj[1] > p[1]) {
            let x_int = (vj[0] - vi[0]) * (p[1] - vi[1]) / (vj[1] - vi[1]) + vi[0];
            if p[0] < x_int {
                inside = !inside;
            }
        }
        j = i;
    }
    inside
}

/// Split an absolute boundary into the `(f32 offsets, f64 origin)` pair that
/// `HatchModel` expects: the origin anchors on the first vertex in full f64 so a
/// typed coordinate (issue #311) and large/UTM positions keep their precision,
/// and `add_hatch` reconstructs each WCS vertex as `origin + offset`. A zero
/// origin with absolute f32 offsets — the previous command output — quantized
/// typed points and mis-placed the fill at large coordinates.
fn rte_boundary(pts: impl Iterator<Item = (f64, f64)>) -> (Vec<[f32; 2]>, [f64; 2]) {
    let pts: Vec<(f64, f64)> = pts.collect();
    let Some(&(ox, oy)) = pts.first() else {
        return (vec![], [0.0; 2]);
    };
    let rel = pts
        .iter()
        .map(|&(x, y)| [(x - ox) as f32, (y - oy) as f32])
        .collect();
    (rel, [ox, oy])
}

// ── HATCH command ──────────────────────────────────────────────────────────

pub struct HatchCommand {
    outlines: Vec<Vec<[f32; 2]>>,
    mode: Mode,
    manual_pts: Vec<DVec3>,
    missed: bool,
}

impl HatchCommand {
    pub fn new(outlines: Vec<Vec<[f32; 2]>>) -> Self {
        Self {
            outlines,
            mode: Mode::PickInside,
            manual_pts: vec![],
            missed: false,
        }
    }

    fn make_hatch(&self, boundary_wcs: Vec<[f64; 2]>) -> HatchModel {
        let (rel, origin) = rte_boundary(boundary_wcs.iter().map(|&[x, y]| (x, y)));
        // Default: ANSI31 from catalog; fallback to a single 45° family.
        let pat_name = "ANSI31";
        let families = crate::scene::model::hatch_patterns::find(pat_name)
            .and_then(|e| {
                if let HatchPattern::Pattern(f) = &e.gpu {
                    Some(f.clone())
                } else {
                    None
                }
            })
            .unwrap_or_else(|| {
                // 45° lines, perpendicular spacing ≈ 5 world units.
                let dy = 5.0_f32 / (45.0_f32.to_radians().cos());
                vec![PatFamily {
                    angle_deg: 45.0,
                    x0: 0.0,
                    y0: 0.0,
                    dx: 0.0,
                    dy,
                    dashes: vec![],
                }]
            });
        HatchModel {
            boundary: std::sync::Arc::new(rel),
            pattern: HatchPattern::Pattern(families),
            name: pat_name.into(),
            color: [0.75, 0.75, 0.75, 0.85],
            angle_offset: 0.0,
            scale: 1.0,
            world_origin: origin,
            boundary_wcs: Some(std::sync::Arc::new(boundary_wcs)),
            vp_scissor: None,
            draw_depth: 0.0,
        }
    }
}

impl CadCommand for HatchCommand {
    fn name(&self) -> &'static str {
        "HATCH"
    }

    fn prompt(&self) -> String {
        match &self.mode {
            Mode::PickInside => {
                let miss = if self.missed {
                    "  ⚠ No closed boundary found."
                } else {
                    ""
                };
                format!("HATCH  Pick internal point:{miss}")
            }
            Mode::Manual => {
                if self.manual_pts.is_empty() {
                    "HATCH  Boundary point 1:".into()
                } else {
                    format!("HATCH  Point {}:", self.manual_pts.len() + 1)
                }
            }
        }
    }

    fn options(&self) -> Vec<crate::command::CmdOption> {
        use crate::command::CmdOption;
        match &self.mode {
            Mode::PickInside => vec![CmdOption::new("Draw manually", "S")],
            Mode::Manual => {
                // Enter accepts the boundary once at least 3 points are picked.
                if self.manual_pts.len() >= 3 {
                    vec![CmdOption::enter("Accept")]
                } else {
                    vec![]
                }
            }
        }
    }

    fn on_point(&mut self, pt: DVec3) -> CmdResult {
        match &self.mode {
            Mode::PickInside => {
                // Hit-test against the f32 outline catalog (screen-space).
                let xy = [pt.x as f32, pt.y as f32];
                for outline in &self.outlines {
                    if point_in_polygon(xy, outline) {
                        self.missed = false;
                        let wcs = outline.iter().map(|&[x, y]| [x as f64, y as f64]).collect();
                        return CmdResult::CommitHatch(self.make_hatch(wcs));
                    }
                }
                self.missed = true;
                CmdResult::NeedPoint
            }
            Mode::Manual => {
                // Keep the typed/snapped point exact (issue #311).
                self.manual_pts.push(pt);
                CmdResult::NeedPoint
            }
        }
    }

    fn on_enter(&mut self) -> CmdResult {
        match &self.mode {
            Mode::PickInside => CmdResult::Cancel,
            Mode::Manual => {
                if self.manual_pts.len() < 3 {
                    return CmdResult::Cancel;
                }
                let wcs = self.manual_pts.iter().map(|p| [p.x, p.y]).collect();
                CmdResult::CommitHatch(self.make_hatch(wcs))
            }
        }
    }

    fn on_escape(&mut self) -> CmdResult {
        CmdResult::Cancel
    }

    fn wants_text_input(&self) -> bool {
        matches!(self.mode, Mode::PickInside)
    }

    fn on_text_input(&mut self, text: &str) -> Option<CmdResult> {
        if text.trim().eq_ignore_ascii_case("s") {
            self.mode = Mode::Manual;
            self.missed = false;
            return Some(CmdResult::NeedPoint);
        }
        None
    }

    fn on_mouse_move(&mut self, pt: DVec3) -> Option<WireModel> { let pt = pt.as_vec3();
        if let Mode::Manual = &self.mode {
            if self.manual_pts.is_empty() {
                return None;
            }
            let mut pts: Vec<[f32; 3]> = self
                .manual_pts
                .iter()
                .map(|p| [p.x as f32, p.y as f32, p.z as f32])
                .collect();
            pts.push([pt.x, pt.y, pt.z]);
            pts.push([
                self.manual_pts[0].x as f32,
                self.manual_pts[0].y as f32,
                self.manual_pts[0].z as f32,
            ]);
            return Some(WireModel::solid(
                "rubber_band".into(),
                pts,
                WireModel::CYAN,
                false,
            ));
        }
        None
    }
}

// ── GRADIENT command ───────────────────────────────────────────────────────

pub struct GradientCommand {
    outlines: Vec<Vec<[f32; 2]>>,
    mode: Mode,
    manual_pts: Vec<DVec3>,
    missed: bool,
}

impl GradientCommand {
    pub fn new(outlines: Vec<Vec<[f32; 2]>>) -> Self {
        Self {
            outlines,
            mode: Mode::PickInside,
            manual_pts: vec![],
            missed: false,
        }
    }

    fn make_hatch(&self, boundary_wcs: Vec<[f64; 2]>) -> HatchModel {
        let (rel, origin) = rte_boundary(boundary_wcs.iter().map(|&[x, y]| (x, y)));
        HatchModel {
            boundary: std::sync::Arc::new(rel),
            pattern: HatchPattern::Gradient {
                angle_deg: 0.0,
                color2: [0.18, 0.18, 0.18, 0.0],
            },
            name: "LINEAR".into(),
            color: [0.30, 0.60, 0.95, 0.80],
            angle_offset: 0.0,
            scale: 1.0,
            world_origin: origin,
            boundary_wcs: Some(std::sync::Arc::new(boundary_wcs)),
            vp_scissor: None,
            draw_depth: 0.0,
        }
    }
}

impl CadCommand for GradientCommand {
    fn name(&self) -> &'static str {
        "GRADIENT"
    }

    fn prompt(&self) -> String {
        match &self.mode {
            Mode::PickInside => {
                let miss = if self.missed {
                    "  ⚠ No closed boundary found."
                } else {
                    ""
                };
                format!("GRADIENT  Pick internal point:{miss}")
            }
            Mode::Manual => {
                if self.manual_pts.is_empty() {
                    "GRADIENT  Boundary point 1:".into()
                } else {
                    format!("GRADIENT  Point {}:", self.manual_pts.len() + 1)
                }
            }
        }
    }

    fn options(&self) -> Vec<crate::command::CmdOption> {
        use crate::command::CmdOption;
        match &self.mode {
            Mode::PickInside => vec![CmdOption::new("Draw manually", "S")],
            Mode::Manual => {
                // Enter accepts the boundary once at least 3 points are picked.
                if self.manual_pts.len() >= 3 {
                    vec![CmdOption::enter("Accept")]
                } else {
                    vec![]
                }
            }
        }
    }

    fn on_point(&mut self, pt: DVec3) -> CmdResult {
        match &self.mode {
            Mode::PickInside => {
                // Hit-test against the f32 outline catalog (screen-space).
                let xy = [pt.x as f32, pt.y as f32];
                for outline in &self.outlines {
                    if point_in_polygon(xy, outline) {
                        self.missed = false;
                        let wcs = outline.iter().map(|&[x, y]| [x as f64, y as f64]).collect();
                        return CmdResult::CommitHatch(self.make_hatch(wcs));
                    }
                }
                self.missed = true;
                CmdResult::NeedPoint
            }
            Mode::Manual => {
                // Keep the typed/snapped point exact (issue #311).
                self.manual_pts.push(pt);
                CmdResult::NeedPoint
            }
        }
    }

    fn on_enter(&mut self) -> CmdResult {
        match &self.mode {
            Mode::PickInside => CmdResult::Cancel,
            Mode::Manual => {
                if self.manual_pts.len() < 3 {
                    return CmdResult::Cancel;
                }
                let wcs = self.manual_pts.iter().map(|p| [p.x, p.y]).collect();
                CmdResult::CommitHatch(self.make_hatch(wcs))
            }
        }
    }

    fn on_escape(&mut self) -> CmdResult {
        CmdResult::Cancel
    }

    fn wants_text_input(&self) -> bool {
        matches!(self.mode, Mode::PickInside)
    }

    fn on_text_input(&mut self, text: &str) -> Option<CmdResult> {
        if text.trim().eq_ignore_ascii_case("s") {
            self.mode = Mode::Manual;
            self.missed = false;
            return Some(CmdResult::NeedPoint);
        }
        None
    }

    fn on_mouse_move(&mut self, pt: DVec3) -> Option<WireModel> { let pt = pt.as_vec3();
        if let Mode::Manual = &self.mode {
            if self.manual_pts.is_empty() {
                return None;
            }
            let mut pts: Vec<[f32; 3]> = self
                .manual_pts
                .iter()
                .map(|p| [p.x as f32, p.y as f32, p.z as f32])
                .collect();
            pts.push([pt.x, pt.y, pt.z]);
            pts.push([
                self.manual_pts[0].x as f32,
                self.manual_pts[0].y as f32,
                self.manual_pts[0].z as f32,
            ]);
            return Some(WireModel::solid(
                "rubber_band".into(),
                pts,
                WireModel::CYAN,
                false,
            ));
        }
        None
    }
}

// ── BOUNDARY command ───────────────────────────────────────────────────────

pub struct BoundaryCommand {
    outlines: Vec<Vec<[f32; 2]>>,
    missed: bool,
}

impl BoundaryCommand {
    pub fn new(outlines: Vec<Vec<[f32; 2]>>) -> Self {
        Self {
            outlines,
            missed: false,
        }
    }
}

impl CadCommand for BoundaryCommand {
    fn name(&self) -> &'static str {
        "BOUNDARY"
    }

    fn prompt(&self) -> String {
        let miss = if self.missed {
            "  ⚠ No closed boundary found."
        } else {
            ""
        };
        format!("BOUNDARY  Pick internal point:{miss}")
    }

    fn on_point(&mut self, pt: DVec3) -> CmdResult {
        // Hit-test against the f32 outline catalog (screen-space).
        let xy = [pt.x as f32, pt.y as f32];
        for outline in &self.outlines {
            if point_in_polygon(xy, outline) {
                self.missed = false;
                // Store as a Hatch entity (solid fill) so it is selectable.
                let wcs: Vec<[f64; 2]> =
                    outline.iter().map(|&[x, y]| [x as f64, y as f64]).collect();
                let (rel, origin) = rte_boundary(wcs.iter().map(|&[x, y]| (x, y)));
                let model = HatchModel {
                    boundary: std::sync::Arc::new(rel),
                    pattern: HatchPattern::Solid,
                    name: "SOLID".into(),
                    color: [0.45, 0.45, 0.45, 0.60],
                    angle_offset: 0.0,
                    scale: 1.0,
                    world_origin: origin,
                    boundary_wcs: Some(std::sync::Arc::new(wcs)),
                    vp_scissor: None,
                    draw_depth: 0.0,
                };
                return CmdResult::CommitHatch(model);
            }
        }
        self.missed = true;
        CmdResult::NeedPoint
    }

    fn on_enter(&mut self) -> CmdResult {
        CmdResult::Cancel
    }
    fn on_escape(&mut self) -> CmdResult {
        CmdResult::Cancel
    }
}


// ── Autocomplete registry ─────────────────────────────────
inventory::submit!(crate::command::CommandRegistration { names: &["BOUNDARY"] });  // BoundaryCommand
inventory::submit!(crate::command::CommandRegistration { names: &["GRADIENT"] });  // GradientCommand
inventory::submit!(crate::command::CommandRegistration { names: &["HATCH"] });  // HatchCommand
