// Shared B-spline utilities for modify commands (TRIM, BREAK, OFFSET, LENGTHEN).
//
// Provides:
//   - spline_to_bspline   : acadrust Spline → truck BSplineCurve<Point3>
//   - bspline_to_spline   : truck BSplineCurve<Point3> → acadrust Spline
//   - spline_sample_xy    : sample the DXF-XY projection at N+1 points (with t params)
//   - spline_nearest_t    : find the spline parameter t closest to a DXF-XY click
//   - spline_pts_wire     : world-space wire points for WireModel preview

use acadrust::entities::Spline;
use acadrust::types::Vector3;
use acadrust::Handle;
use truck_modeling::base::{BoundedCurve, ParametricCurve};
use truck_modeling::{BSplineCurve, KnotVec, Point3};

// ── Conversion ─────────────────────────────────────────────────────────────

/// Convert an acadrust `Spline` to a truck `BSplineCurve<Point3>`.
/// Returns `None` if the spline has too few control points or inconsistent data.
pub fn spline_to_bspline(spl: &Spline) -> Option<BSplineCurve<Point3>> {
    let ctrl_pts: Vec<Point3> = spl
        .control_points
        .iter()
        .map(|p| Point3::new(p.x, p.y, p.z))
        .collect();
    if ctrl_pts.len() < 2 {
        return None;
    }
    let degree = spl.degree as usize;
    let expected_knots = ctrl_pts.len() + degree + 1;
    let knot_vec = if spl.knots.len() == expected_knots {
        KnotVec::from(spl.knots.clone())
    } else {
        KnotVec::uniform_knot(degree, ctrl_pts.len() - 1)
    };
    Some(BSplineCurve::new(knot_vec, ctrl_pts))
}

/// Rebuild an acadrust `Spline` from a trimmed `BSplineCurve<Point3>`.
/// The `template` spline provides the entity common data, degree, and Z-elevation.
pub fn bspline_to_spline(bs: &BSplineCurve<Point3>, template: &Spline) -> Spline {
    let z = template.control_points.first().map(|v| v.z).unwrap_or(0.0);
    let mut spl = template.clone();
    spl.common.handle = Handle::NULL;
    spl.degree = bs.degree() as i32;
    spl.knots = bs.knot_vec().iter().copied().collect();
    spl.control_points = bs
        .control_points()
        .iter()
        .map(|p| Vector3::new(p.x, p.y, z))
        .collect();
    spl.weights.clear(); // not rational after split
    spl.fit_points.clear(); // fit points are no longer valid
    spl
}

// ── Sampling ───────────────────────────────────────────────────────────────

/// Sample the spline's DXF-XY projection at `n+1` evenly-spaced parameter
/// values.  Returns `(t_params, xy_points)` both of length `n+1`.
pub fn spline_sample_xy(spl: &Spline, n: usize) -> (Vec<f64>, Vec<[f64; 2]>) {
    let bs = match spline_to_bspline(spl) {
        Some(b) => b,
        None => return (vec![], vec![]),
    };
    let (t0, t1) = bs.range_tuple();
    let ts: Vec<f64> = (0..=n)
        .map(|i| t0 + (t1 - t0) * (i as f64 / n as f64))
        .collect();
    let pts: Vec<[f64; 2]> = ts
        .iter()
        .map(|&t| {
            let p = bs.subs(t);
            [p.x, p.y]
        })
        .collect();
    (ts, pts)
}

/// Find the spline parameter `t` (in the knot-vector range [t0, t1]) that is
/// closest to the DXF-XY point `(x, y)`.
/// Uses 64-sample coarse search followed by bisection.
pub fn spline_nearest_t(spl: &Spline, x: f64, y: f64) -> Option<f64> {
    let bs = spline_to_bspline(spl)?;
    let (t0, t1) = bs.range_tuple();
    let n = 64usize;
    let step = (t1 - t0) / n as f64;

    // Coarse search
    let mut best_t = t0;
    let mut best_d = f64::MAX;
    for i in 0..=n {
        let t = t0 + i as f64 * step;
        let p = bs.subs(t);
        let d = (p.x - x).powi(2) + (p.y - y).powi(2);
        if d < best_d {
            best_d = d;
            best_t = t;
        }
    }

    // Bisection refinement in [best_t - step, best_t + step]
    let lo = (best_t - step).max(t0);
    let hi = (best_t + step).min(t1);
    let mut a = lo;
    let mut b = hi;
    for _ in 0..32 {
        let m1 = a + (b - a) / 3.0;
        let m2 = b - (b - a) / 3.0;
        let p1 = bs.subs(m1);
        let p2 = bs.subs(m2);
        let d1 = (p1.x - x).powi(2) + (p1.y - y).powi(2);
        let d2 = (p2.x - x).powi(2) + (p2.y - y).powi(2);
        if d1 < d2 {
            b = m2;
        } else {
            a = m1;
        }
    }
    Some((a + b) * 0.5)
}

/// Returns the normalised parameter in [0, 1] given an actual B-spline
/// parameter `t_actual` and the range `[t0, t1]`.
pub fn t_to_rel(t_actual: f64, t0: f64, t1: f64) -> f64 {
    if (t1 - t0).abs() < 1e-12 {
        return 0.0;
    }
    ((t_actual - t0) / (t1 - t0)).clamp(0.0, 1.0)
}

// ── Wire preview ───────────────────────────────────────────────────────────

/// World-space wire points for a Spline (samples 64 segments).
/// Drawing plane is world XY: DXF (x, y) → world (x, y), z = elevation.
pub fn spline_pts_wire(spl: &Spline) -> Vec<[f32; 3]> {
    let (_, pts) = spline_sample_xy(spl, 64);
    if pts.is_empty() {
        return vec![];
    }
    let elev = spl
        .control_points
        .first()
        .map(|v| v.z as f32)
        .unwrap_or(0.0);
    pts.iter()
        .map(|p| [p[0] as f32, p[1] as f32, elev])
        .collect()
}
