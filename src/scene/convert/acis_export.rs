//! Export a truck B-rep `Solid` to an exact ACIS `SatDocument`.
//!
//! OCS models 3-D solids with truck (`scene.solid_models`), but EXTRUDE /
//! REVOLVE / SWEEP / LOFT / boolean results carry no ACIS geometry, so other
//! CAD applications drop them on open. Converting the truck solid to ACIS lets
//! the DWG/DXF writer store real modeler geometry.
//!
//! This module handles the **planar** case: a solid whose faces are all planes
//! bounded by straight edges (boxes, extruded polygons, planar boolean results).
//! It walks the topology into a vertex/face-ring mesh and hands it to acadrust's
//! [`build_planar_body`], which assembles the exact B-rep. Any curved face or
//! edge makes it return `None` — those solids are left for the NURBS path.

use std::collections::HashMap;

use acadrust::entities::acis::{primitives::build_planar_body, SatDocument};
use truck_modeling::{Curve, Solid, Surface};

/// Signed volume × 6 of the closed mesh (positive when every face ring is wound
/// counter-clockwise as seen from outside). Used to make the export independent
/// of truck's face-orientation convention.
fn signed_volume6(vertices: &[[f64; 3]], faces: &[Vec<usize>]) -> f64 {
    let mut acc = 0.0;
    for f in faces {
        let a = vertices[f[0]];
        // Fan-triangulate the (planar, convex-or-not) ring from its first vertex.
        for i in 1..f.len() - 1 {
            let b = vertices[f[i]];
            let c = vertices[f[i + 1]];
            acc += a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0]);
        }
    }
    acc
}

/// Build an exact ACIS `SatDocument` from a truck solid whose faces are all
/// planar and edges all straight. Returns `None` for any curved face/edge (left
/// for the NURBS export), for faces with holes, or for a degenerate body.
pub fn planar_solid_to_sat(solid: &Solid) -> Option<SatDocument> {
    let mut positions: Vec<[f64; 3]> = Vec::new();
    let mut vert_index: HashMap<_, usize> = HashMap::new();
    let mut faces: Vec<Vec<usize>> = Vec::new();

    for shell in solid.boundaries() {
        for face in shell.face_iter() {
            // Planar faces only — a curved surface needs the NURBS path.
            if !matches!(face.surface(), Surface::Plane(_)) {
                return None;
            }
            // Single outer loop only (no holes) in the planar path.
            let boundaries = face.boundaries();
            if boundaries.len() != 1 {
                return None;
            }
            let wire = &boundaries[0];

            // Every bounding edge must be a straight line.
            for edge in wire.edge_iter() {
                if !matches!(edge.curve(), Curve::Line(_)) {
                    return None;
                }
            }

            // Ordered vertex ring of the loop.
            let mut ring: Vec<usize> = Vec::new();
            for v in wire.vertex_iter() {
                let key = v.id();
                let p = v.point();
                let idx = *vert_index.entry(key).or_insert_with(|| {
                    positions.push([p.x, p.y, p.z]);
                    positions.len() - 1
                });
                // Drop a closing vertex that repeats the ring's start.
                if ring.last() != Some(&idx) {
                    ring.push(idx);
                }
            }
            if ring.len() >= 2 && ring.first() == ring.last() {
                ring.pop();
            }
            if ring.len() < 3 {
                return None;
            }
            faces.push(ring);
        }
    }

    if faces.len() < 4 || positions.len() < 4 {
        return None;
    }

    // Make the winding outward-CCW regardless of truck's convention: a
    // correctly-oriented closed shell has positive signed volume; if it came out
    // negative every ring is inside-out, so reverse them all.
    if signed_volume6(&positions, &faces) < 0.0 {
        for f in faces.iter_mut() {
            f.reverse();
        }
    }

    build_planar_body(&positions, &faces)
}

#[cfg(test)]
mod tests {
    use super::*;
    use truck_modeling::builder;
    use truck_modeling::{Point3, Vector3};

    /// A truck box (dimension-raising sweep vertex→edge→face→solid) must export
    /// to a valid 6-face / 12-edge / 8-vertex ACIS body.
    #[test]
    fn box_exports_to_valid_planar_sat() {
        let p = builder::vertex(Point3::new(0.0, 0.0, 0.0));
        let e = builder::tsweep(&p, Vector3::new(2.0, 0.0, 0.0));
        let f = builder::tsweep(&e, Vector3::new(0.0, 2.0, 0.0));
        let solid = builder::tsweep(&f, Vector3::new(0.0, 0.0, 2.0));

        let sat = planar_solid_to_sat(&solid).expect("box should export to SAT");
        assert_eq!(sat.faces().len(), 6, "box has 6 planar faces");
        assert_eq!(sat.edges().len(), 12, "box has 12 straight edges");
        assert_eq!(sat.vertices().len(), 8, "box has 8 vertices");
        assert!(
            sat.validate().is_empty(),
            "exported box failed ACIS validation: {:?}",
            sat.validate()
        );
    }
}
