//! Uniform spatial grid over a hit-test wire set's world-XY AABBs.
//!
//! Snap and hover hit-testing scan the full model wire set on every cursor
//! move. On a heavily block-instanced drawing that set explodes to millions of
//! wires, so an O(N) per-move scan — even with a cheap AABB reject — stalls the
//! event loop. This grid is built once per geometry epoch (cached alongside the
//! wire set) and answers "which wires are near this cursor point" in O(cells in
//! range), turning the per-move cost from O(all wires) into O(local).
//!
//! Wires whose AABB is unbounded (previews / entities with no usable
//! bounding box) or spans a large fraction of the grid (drawing-length lines)
//! go into an always-checked `oversized` list rather than being smeared across
//! thousands of cells.

use crate::scene::model::wire_model::WireModel;

/// A wire spanning more than this many cells is stored once in `oversized`
/// instead of being inserted into every overlapped cell.
const MAX_SPAN_CELLS: u64 = 64;

pub struct WireGrid {
    min: [f64; 2],
    cell: f64,
    cols: u32,
    rows: u32,
    cells: Vec<Vec<u32>>,
    /// Indices always returned as candidates (unbounded / huge AABB).
    oversized: Vec<u32>,
}

impl WireGrid {
    fn finite_aabb(w: &WireModel) -> Option<[f64; 4]> {
        let a = w.aabb;
        (a[0].is_finite() && a[1].is_finite() && a[2].is_finite() && a[3].is_finite())
            .then_some([a[0] as f64, a[1] as f64, a[2] as f64, a[3] as f64])
    }

    pub fn build(wires: &[WireModel]) -> Self {
        // Overall finite extent.
        let mut min = [f64::INFINITY; 2];
        let mut max = [f64::NEG_INFINITY; 2];
        for w in wires {
            if let Some(a) = Self::finite_aabb(w) {
                min[0] = min[0].min(a[0]);
                min[1] = min[1].min(a[1]);
                max[0] = max[0].max(a[2]);
                max[1] = max[1].max(a[3]);
            }
        }
        if !min[0].is_finite() {
            // No finite wires — everything is oversized (always checked).
            return Self {
                min: [0.0, 0.0],
                cell: 1.0,
                cols: 1,
                rows: 1,
                cells: vec![Vec::new()],
                oversized: (0..wires.len() as u32).collect(),
            };
        }
        let ext_x = (max[0] - min[0]).max(1e-6);
        let ext_y = (max[1] - min[1]).max(1e-6);
        // Aim for ~8 wires/cell; a square-ish cell keeps queries tight.
        let target_cells = ((wires.len() / 8).max(1)) as f64;
        let cell = ((ext_x * ext_y) / target_cells).sqrt().max(1e-6);
        let cols = (((ext_x / cell).ceil() as i64) + 1).clamp(1, 8192) as u32;
        let rows = (((ext_y / cell).ceil() as i64) + 1).clamp(1, 8192) as u32;

        let mut cells = vec![Vec::<u32>::new(); (cols as usize) * (rows as usize)];
        let mut oversized = Vec::new();

        let col_of = |x: f64| (((x - min[0]) / cell).floor()).clamp(0.0, (cols - 1) as f64) as u32;
        let row_of = |y: f64| (((y - min[1]) / cell).floor()).clamp(0.0, (rows - 1) as f64) as u32;

        for (idx, w) in wires.iter().enumerate() {
            let Some(a) = Self::finite_aabb(w) else {
                oversized.push(idx as u32);
                continue;
            };
            let c0 = col_of(a[0]);
            let c1 = col_of(a[2]);
            let r0 = row_of(a[1]);
            let r1 = row_of(a[3]);
            let span = (c1 - c0 + 1) as u64 * (r1 - r0 + 1) as u64;
            if span > MAX_SPAN_CELLS {
                oversized.push(idx as u32);
                continue;
            }
            for r in r0..=r1 {
                let base = (r * cols) as usize;
                for c in c0..=c1 {
                    cells[base + c as usize].push(idx as u32);
                }
            }
        }

        Self {
            min,
            cell,
            cols,
            rows,
            cells,
            oversized,
        }
    }

    /// Candidate wire indices whose cell overlaps the `radius`-padded box around
    /// `(x, y)`. Always includes the oversized list. May contain a wire more
    /// than once is avoided by dedup.
    pub fn query(&self, x: f64, y: f64, radius: f64) -> Vec<u32> {
        let r = radius.max(0.0);
        let mut out = self.oversized.clone();
        // Query box fully outside the grid → only oversized candidates.
        if x + r < self.min[0]
            || y + r < self.min[1]
            || x - r > self.min[0] + self.cols as f64 * self.cell
            || y - r > self.min[1] + self.rows as f64 * self.cell
        {
            return out;
        }
        let clampc = |v: f64| v.clamp(0.0, (self.cols - 1) as f64) as u32;
        let clampr = |v: f64| v.clamp(0.0, (self.rows - 1) as f64) as u32;
        let c0 = clampc(((x - r) - self.min[0]) / self.cell);
        let c1 = clampc(((x + r) - self.min[0]) / self.cell);
        let r0 = clampr(((y - r) - self.min[1]) / self.cell);
        let r1 = clampr(((y + r) - self.min[1]) / self.cell);
        for row in r0..=r1 {
            let base = (row * self.cols) as usize;
            for col in c0..=c1 {
                out.extend_from_slice(&self.cells[base + col as usize]);
            }
        }
        out.sort_unstable();
        out.dedup();
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn wire(x: f32, y: f32) -> WireModel {
        let mut w = WireModel::solid_f64("t".into(), vec![[x as f64, y as f64, 0.0]], [0.0; 4], false);
        w.aabb = [x, y, x, y];
        w
    }

    #[test]
    fn query_is_local_and_hits_the_point() {
        // 50×50 lattice of point-wires spaced 10 apart (2500 wires).
        let mut wires = Vec::new();
        for gx in 0..50 {
            for gy in 0..50 {
                wires.push(wire(gx as f32 * 10.0, gy as f32 * 10.0));
            }
        }
        let n = wires.len();
        let grid = WireGrid::build(&wires);
        // Tight query around one lattice point.
        let hits = grid.query(250.0, 250.0, 5.0);
        assert!(hits.len() < n / 10, "query too broad: {} of {n}", hits.len());
        let idx = (25u32 * 50) + 25; // gx=25, gy=25
        assert!(hits.contains(&idx), "the on-point wire must be a candidate");
        // A far point must not drag in the whole lattice.
        let far = grid.query(-9999.0, -9999.0, 5.0);
        assert!(far.len() < n / 10, "far query too broad: {}", far.len());
    }

    #[test]
    fn unbounded_wire_is_always_a_candidate() {
        let mut wires = vec![wire(0.0, 0.0), wire(1_000_000.0, 1_000_000.0)];
        wires[1].aabb = WireModel::UNBOUNDED_AABB;
        let grid = WireGrid::build(&wires);
        let hits = grid.query(0.0, 0.0, 1.0);
        assert!(hits.contains(&1), "unbounded wire must always be returned");
    }
}
