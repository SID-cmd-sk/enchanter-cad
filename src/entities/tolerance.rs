use acadrust::entities::Tolerance;

use crate::command::EntityTransform;
use crate::entities::common::{edit_prop as edit, ro_prop as ro, square_grip};
use crate::entities::traits::{Grippable, PropertyEditable, Transformable, TruckConvertible};
use crate::scene::convert::acad_to_truck::{GlyphRun, TextStroke, TruckEntity, TruckObject};
use crate::scene::model::object::{GripApply, GripDef, PropSection};
use crate::scene::model::wire_model::SnapHint;
use crate::scene::text::lff;
use crate::scene::view::transform;

// ── GDT text parser ───────────────────────────────────────────────────────────

/// Parse a DXF tolerance text string into rows of cell strings.
///
/// DXF format:  `{\Fgdt;p}%%v0.5%%vA%%vB%%v%%v^J{\Fgdt;j}%%v0.1%%vA%%v%%v%%v`
///   - `^J`  → row separator
///   - `%%v` → cell separator within a row
///   - `{\Fgdt;X}` → GDT symbol X (mapped to a text label)
fn parse_gdt_rows(raw: &str) -> Vec<Vec<String>> {
    raw.split("^J")
        .filter(|row| !row.trim().is_empty())
        .map(|row| {
            row.split("%%v")
                .map(|cell| substitute_gdt_codes(cell.trim()))
                .collect()
        })
        .collect()
}

/// Replace `{\Fgdt;X}` sequences with a short ASCII label and strip other
/// MTEXT-style format codes `{\...}`.
fn substitute_gdt_codes(s: &str) -> String {
    let mut out = String::new();
    let mut chars = s.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch == '{' {
            // Collect to closing '}'
            let mut inner = String::new();
            let mut depth = 1usize;
            for c in chars.by_ref() {
                match c {
                    '{' => {
                        depth += 1;
                        inner.push(c);
                    }
                    '}' => {
                        depth -= 1;
                        if depth == 0 {
                            break;
                        }
                        inner.push(c);
                    }
                    _ => {
                        inner.push(c);
                    }
                }
            }
            // Is it a GDT font switch?
            if let Some(rest) = inner.strip_prefix("\\Fgdt;") {
                // rest is the symbol letter(s)
                if let Some(sym_char) = rest.chars().next() {
                    out.push_str(gdt_char_to_ascii(sym_char));
                }
            }
            // other format codes: skip
        } else {
            out.push(ch);
        }
    }
    out
}

/// Map a GDT font character to a short ASCII approximation.
fn gdt_char_to_ascii(c: char) -> &'static str {
    match c {
        'a' => "SRT", // Straightness
        'b' => "FLT", // Flatness
        'c' => "FLT", // Flatness
        'd' => "PSF", // Profile of Surface
        'e' => "CYL", // Cylindricity
        'f' => "PRL", // Profile of Line
        'g' => "CIR", // Circularity
        'h' => "PAR", // Parallelism
        'i' => "SYM", // Symmetry
        'j' => "PRP", // Perpendicularity
        'k' => "PLN", // Profile of Line
        'l' => "(L)", // LMC
        'm' => "(M)", // MMC / Diameter
        'n' => "ANG", // Angularity
        'o' => "(o)", // at maximum material boundary
        'p' => "POS", // Position
        'q' => "(q)",
        'r' => "RUN", // Circular Runout
        's' => "(S)", // RFS / Regardless of Feature Size
        't' => "TRN", // Total Runout
        'u' => "CON", // Concentricity
        'v' => "(v)",
        'w' => "(w)",
        _ => "?",
    }
}

// ── Feature-control frame builder ─────────────────────────────────────────────

/// One text cell of a feature-control frame, ready to become a `TextStroke`
/// with a `GlyphRun` so the cell text can render as SDF glyph quads (or, when
/// SDF is off, from `strokes`). `origin` is relative to the tolerance insertion
/// point (already rotated); `strokes` are the glyph polylines rotated about the
/// origin (no origin translation — the wire-builder adds the origin).
struct TolCell {
    text: String,
    origin: [f32; 2],
    strokes: Vec<Vec<[f32; 2]>>,
    height: f32,
    rotation: f32,
}

/// Tessellate a Tolerance entity's feature-control frame.
///
/// Returns (`box_strokes`, `cells`):
///   - `box_strokes` — the outer border, row separators and column dividers as
///     2-D polylines (rotated; run-less, so they always render as strokes)
///   - `cells` — one [`TolCell`] per non-empty cell, carrying its text + a
///     `GlyphRun` so the cell renders as SDF text (frame stays geometry).
fn tessellate_tolerance(tol: &Tolerance) -> (Vec<Vec<[f32; 2]>>, Vec<TolCell>) {
    if tol.text.is_empty() {
        return (vec![], vec![]);
    }

    let rows = parse_gdt_rows(&tol.text);
    if rows.is_empty() {
        return (vec![], vec![]);
    }

    // ── Metrics ──────────────────────────────────────────────────────────
    let h = if tol.text_height > 1e-6 {
        tol.text_height as f32
    } else {
        2.5_f32
    };
    // DIMGAP — stored on the entity (resolved from the dim style at creation).
    // Fall back to AutoCAD's 0.35 × height convention only when missing.
    let gap = if tol.dimension_gap > 1e-6 {
        tol.dimension_gap as f32
    } else {
        (h * 0.35).max(0.1)
    };
    let cell_h = h + 2.0 * gap;
    let char_w = h * 0.65;
    let min_cell_w = h * 1.4;

    // Column widths: max across all rows
    let max_cols = rows.iter().map(|r| r.len()).max().unwrap_or(0);
    let mut col_widths: Vec<f32> = vec![0.0_f32; max_cols];
    for row in &rows {
        for (ci, cell) in row.iter().enumerate() {
            let w = (cell.len() as f32 * char_w).max(min_cell_w);
            if ci < col_widths.len() {
                col_widths[ci] = col_widths[ci].max(w);
            }
        }
    }
    let total_w: f32 = col_widths.iter().sum();
    let total_h = cell_h * rows.len() as f32;

    // ── Transform helpers (local space — translation applied in tessellate.rs) ──
    let angle = (tol.direction.y as f32).atan2(tol.direction.x as f32);
    let (sa, ca) = angle.sin_cos();

    // Rotate only; origin is kept as f64 and applied later with full precision.
    let rot = |x: f32, y: f32| -> [f32; 2] { [x * ca - y * sa, x * sa + y * ca] };

    let mut box_out: Vec<Vec<[f32; 2]>> = Vec::new();
    let mut cells: Vec<TolCell> = Vec::new();

    // ── Outer border ──────────────────────────────────────────────────────
    box_out.push(vec![
        rot(0.0, 0.0),
        rot(total_w, 0.0),
        rot(total_w, total_h),
        rot(0.0, total_h),
        rot(0.0, 0.0),
    ]);

    // ── Row separators ─────────────────────────────────────────────────────
    for ri in 1..rows.len() {
        let y = cell_h * ri as f32;
        box_out.push(vec![rot(0.0, y), rot(total_w, y)]);
    }

    // ── Column dividers ────────────────────────────────────────────────────
    let mut x_cursor = 0.0_f32;
    for ci in 0..col_widths.len().saturating_sub(1) {
        x_cursor += col_widths[ci];
        for ri in 0..rows.len() {
            if ci + 1 < rows[ri].len() {
                let y0 = cell_h * ri as f32;
                let y1 = y0 + cell_h;
                box_out.push(vec![rot(x_cursor, y0), rot(x_cursor, y1)]);
            }
        }
    }

    // ── Text content per cell ─────────────────────────────────────────────
    // Each cell becomes a TolCell: its origin is the (rotated) cell position
    // relative to the insertion point; its `strokes` are the glyph polylines
    // rotated about that origin (used only when SDF is off). The GlyphRun the
    // caller attaches lets the cell render as SDF text.
    for (ri, row) in rows.iter().enumerate() {
        let row_y = cell_h * ri as f32 + gap;
        let mut cell_x = 0.0_f32;
        for (ci, cell) in row.iter().enumerate() {
            let cw = if ci < col_widths.len() {
                col_widths[ci]
            } else {
                0.0
            };
            if !cell.is_empty() {
                let text_w = cell.len() as f32 * char_w;
                let tx = cell_x + (cw - text_w) * 0.5;
                let (local_strokes, _) =
                    lff::tessellate_text_ex([0.0, 0.0], h, 0.0, 1.0, 0.0, "txt", cell);
                // Glyph polylines rotated about the cell origin (no origin
                // translation — the wire-builder adds `origin`).
                let strokes: Vec<Vec<[f32; 2]>> = local_strokes
                    .into_iter()
                    .map(|pl| pl.into_iter().map(|[px, py]| rot(px, py)).collect())
                    .filter(|pl: &Vec<[f32; 2]>| !pl.is_empty())
                    .collect();
                cells.push(TolCell {
                    text: cell.clone(),
                    origin: rot(tx, row_y),
                    strokes,
                    height: h,
                    rotation: angle,
                });
            }
            cell_x += cw;
        }
    }

    (box_out, cells)
}

// ── TruckConvertible ──────────────────────────────────────────────────────────

impl TruckConvertible for Tolerance {
    fn to_truck(&self, _document: &acadrust::CadDocument) -> Option<TruckEntity> {
        if self.text.is_empty() {
            return None;
        }

        let snap_pt = glam::DVec3::new(
            self.insertion_point.x,
            self.insertion_point.y,
            self.insertion_point.z,
        );

        // Build the feature-control frame in local space; origin stored as f64.
        let (box_strokes, cells) = tessellate_tolerance(self);
        let ins = [self.insertion_point.x, self.insertion_point.y];

        // Frame geometry first (run-less → always strokes; also the anchor
        // group so its origin = the insertion point), then one run-group per
        // text cell so the cell text renders as SDF glyphs (or strokes when
        // SDF is off).
        let mut groups: Vec<TextStroke> = Vec::with_capacity(1 + cells.len());
        if !box_strokes.is_empty() {
            groups.push(TextStroke {
                strokes: box_strokes,
                origin: ins,
                color: None,
                fill_tris: vec![],
                run: None,
            });
        }
        for cell in cells {
            groups.push(TextStroke {
                strokes: cell.strokes,
                origin: [ins[0] + cell.origin[0] as f64, ins[1] + cell.origin[1] as f64],
                color: None,
                fill_tris: vec![],
                run: Some(GlyphRun {
                    text: cell.text,
                    font: "txt".to_string(),
                    height: cell.height,
                    rotation: cell.rotation,
                    width_factor: 1.0,
                    oblique: 0.0,
                    tracking: 0.0,
                    bold: false,
                }),
            });
        }
        if groups.is_empty() {
            return None;
        }

        Some(TruckEntity {
            object: TruckObject::Text(groups),
            snap_pts: vec![(snap_pt, SnapHint::Insertion)],
            tangent_geoms: vec![],
            key_vertices: vec![],
            fill_tris: vec![],
        })
    }
}

// ── Grippable ─────────────────────────────────────────────────────────────────

impl Grippable for Tolerance {
    fn grips(&self) -> Vec<GripDef> {
        vec![square_grip(
            0,
            glam::DVec3::new(
                self.insertion_point.x,
                self.insertion_point.y,
                self.insertion_point.z,
            ),
        )]
    }

    fn apply_grip(&mut self, grip_id: usize, apply: GripApply) {
        if grip_id == 0 {
            match apply {
                GripApply::Translate(d) => {
                    self.insertion_point.x += d.x as f64;
                    self.insertion_point.y += d.y as f64;
                    self.insertion_point.z += d.z as f64;
                }
                GripApply::Absolute(p) => {
                    self.insertion_point.x = p.x as f64;
                    self.insertion_point.y = p.y as f64;
                    self.insertion_point.z = p.z as f64;
                }
            }
        }
    }
}

// ── PropertyEditable ──────────────────────────────────────────────────────────

impl PropertyEditable for Tolerance {
    fn geometry_properties(&self, _text_style_names: &[String]) -> Vec<PropSection> {
        vec![
            PropSection {
                title: "Text".into(),
                props: vec![
                    ro("Text style", "tol_text_style", String::new()),
                    edit("Text height", "tol_text_height", self.text_height),
                ],
            },
            PropSection {
                title: "Geometry".into(),
                props: vec![
                    edit("Position X", "tol_ix", self.insertion_point.x),
                    edit("Position Y", "tol_iy", self.insertion_point.y),
                    edit("Position Z", "tol_iz", self.insertion_point.z),
                ],
            },
            PropSection {
                title: "Misc".into(),
                props: vec![
                    ro(
                        "Dimension style",
                        "tol_dim_style",
                        if self.dimension_style_name.is_empty() {
                            "(default)".to_string()
                        } else {
                            self.dimension_style_name.clone()
                        },
                    ),
                    edit("Direction X", "tol_dir_x", self.direction.x),
                    edit("Direction Y", "tol_dir_y", self.direction.y),
                    edit("Direction Z", "tol_dir_z", self.direction.z),
                ],
            },
        ]
    }

    fn apply_geom_prop(&mut self, field: &str, value: &str) {
        let Ok(v) = value.trim().parse::<f64>() else {
            return;
        };
        match field {
            "tol_ix" => self.insertion_point.x = v,
            "tol_iy" => self.insertion_point.y = v,
            "tol_iz" => self.insertion_point.z = v,
            "tol_text_height" if v > 0.0 => self.text_height = v,
            "tol_dir_x" => self.direction.x = v,
            "tol_dir_y" => self.direction.y = v,
            "tol_dir_z" => self.direction.z = v,
            _ => {}
        }
    }
}

// ── Transformable ─────────────────────────────────────────────────────────────

impl Transformable for Tolerance {
    fn apply_transform(&mut self, t: &EntityTransform) {
        transform::apply_standard_entity_transform(self, t, |entity, p1, p2| {
            transform::reflect_xy_point(
                &mut entity.insertion_point.x,
                &mut entity.insertion_point.y,
                p1,
                p2,
            );
        });
    }
}
