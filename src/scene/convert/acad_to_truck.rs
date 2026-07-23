// acadrust -> truck topology conversion layer.

use acadrust::{CadDocument, EntityType};
use truck_modeling::{Edge, Solid, Vertex, Wire};

use crate::entities::traits::EntityTypeOps;
use crate::scene::model::wire_model::{SnapHint, TangentGeom};

/// One group of glyph strokes with its world-space origin stored in f64.
/// Strokes are in glyph-local space (origin = [0,0]) so that the large
/// world offset can be subtracted with f64 precision in tessellate.rs.
///
/// `color`, when set, overrides the entity colour for just this group — used
/// by MTEXT inline `\C` / `\c` per-run colour. Strokes sharing the same
/// (color, None) override are merged into one WireModel downstream; runs with
/// distinct colours emit their own WireModel.
pub struct TextStroke {
    pub strokes: Vec<Vec<[f32; 2]>>,
    pub origin: [f64; 2],
    pub color: Option<[f32; 3]>,
    pub fill_tris: Vec<[f32; 2]>,
    /// Layout inputs to rebuild this run as per-glyph SDF quads (see
    /// `scene::text::glyph_quads`). `Some` on runs wired for the SDF text
    /// renderer; `None` leaves the run to the stroke path only. Heights are
    /// raw (pre annotation-scale), matching `strokes` — the SDF collector
    /// applies annotation scale the same way `tessellate` does for strokes.
    pub run: Option<GlyphRun>,
}

/// Per-run text-layout inputs needed to reproduce a run as SDF glyph quads.
#[derive(Clone, Debug)]
pub struct GlyphRun {
    pub text: String,
    pub font: String,
    /// Raw height in drawing units (annotation scale applied later).
    pub height: f32,
    pub rotation: f32,
    pub width_factor: f32,
    pub oblique: f32,
    pub tracking: f32,
    /// Bold run — the SDF glyph bakes with a wider pen (thicker strokes).
    pub bold: bool,
}

#[allow(dead_code)]
pub enum TruckObject {
    Point(Vertex),
    Curve(Edge),
    Contour(Wire),
    Text(Vec<TextStroke>),
    /// Pre-computed NaN-separated 3-D point list (leader lines, arrowheads, etc.).
    /// Points are stored in WCS as **f64** so the large world_offset can be
    /// subtracted in full precision in tessellate.rs before the f32 cast.
    /// Casting WCS coordinates to f32 in the entity converters used to wreck
    /// rotated sub-glyph precision on drawings far from origin.
    Lines(Vec<[f64; 3]>),
    /// Like Lines but linetype pattern restarts at each NaN-separated segment (plinegen=false).
    SegmentedLines(Vec<[f64; 3]>),
    Volume(Solid),
}

pub struct TruckEntity {
    pub object: TruckObject,
    pub snap_pts: Vec<(glam::DVec3, SnapHint)>,
    pub tangent_geoms: Vec<TangentGeom>,
    /// Polyline vertex positions in WCS f64; converted to offset-relative f32
    /// at the wire-model boundary.
    pub key_vertices: Vec<[f64; 3]>,
    /// Pre-triangulated fill geometry: flat list of WCS f64 vertices, 3 per
    /// triangle. Non-empty for mesh-like entities (PolyfaceMesh, PolygonMesh)
    /// that need solid fill.
    pub fill_tris: Vec<[f64; 3]>,
}

pub fn convert(entity: &EntityType, document: &CadDocument) -> Option<TruckEntity> {
    entity.to_truck_entity(document)
}
