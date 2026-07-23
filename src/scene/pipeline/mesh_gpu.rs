// Mesh GPU buffers — TriangleList rendering for solid objects.
//
// Vertex layout (40 bytes):
//   position   [f32; 3]   offset  0   12 B
//   normal     [f32; 3]   offset 12   12 B
//   color      [f32; 4]   offset 24   16 B
//                                ------
//                                 40 B / vertex

use crate::scene::model::mesh_model::{MeshLodSet, MeshModel};
use iced::wgpu;
use iced::wgpu::util::DeviceExt;

// ── Vertex layout ─────────────────────────────────────────────────────────

#[repr(C)]
#[derive(Copy, Clone, bytemuck::Pod, bytemuck::Zeroable)]
pub struct MeshVertex {
    pub position: [f32; 3],
    pub normal: [f32; 3],
    pub color: [f32; 4],
    pub position_low: [f32; 3],
}

impl MeshVertex {
    pub fn layout<'a>() -> wgpu::VertexBufferLayout<'a> {
        const ATTRS: &[wgpu::VertexAttribute] = &[
            wgpu::VertexAttribute {
                offset: std::mem::offset_of!(MeshVertex, position) as u64,
                shader_location: 0,
                format: wgpu::VertexFormat::Float32x3,
            },
            wgpu::VertexAttribute {
                offset: std::mem::offset_of!(MeshVertex, normal) as u64,
                shader_location: 1,
                format: wgpu::VertexFormat::Float32x3,
            },
            wgpu::VertexAttribute {
                offset: std::mem::offset_of!(MeshVertex, color) as u64,
                shader_location: 2,
                format: wgpu::VertexFormat::Float32x4,
            },
            wgpu::VertexAttribute {
                offset: std::mem::offset_of!(MeshVertex, position_low) as u64,
                shader_location: 3,
                format: wgpu::VertexFormat::Float32x3,
            },
        ];
        wgpu::VertexBufferLayout {
            array_stride: std::mem::size_of::<MeshVertex>() as u64,
            step_mode: wgpu::VertexStepMode::Vertex,
            attributes: ATTRS,
        }
    }
}

// ── GPU handle ────────────────────────────────────────────────────────────

pub struct MeshGpu {
    pub vertex_buffer: wgpu::Buffer,
    pub index_buffer: wgpu::Buffer,
    pub index_count: u32,
    /// Line-list index buffer: every triangle `(a, b, c)` from the
    /// solid index buffer is expanded into three segments
    /// `(a,b)(b,c)(c,a)`. Used by the wireframe-mode render path so 3D
    /// solids draw as their triangle edges without needing the
    /// `POLYGON_MODE_LINE` device feature.
    #[allow(dead_code)] // only the highlight overlay builds MeshGpu now (fill only)
    pub wire_index_buffer: wgpu::Buffer,
    #[allow(dead_code)]
    pub wire_index_count: u32,
}

/// GPU-side bundle of MeshLodSet — one MeshGpu per available LOD plus
/// the world-XY AABB needed to pick a level per frame.
pub struct MeshLodGpu {
    pub lods: Vec<MeshGpu>,
    pub world_aabb: [f32; 4],
}

/// How a solid mesh is highlighted this frame.
#[derive(Copy, Clone, PartialEq, Eq)]
pub enum Highlight {
    #[allow(dead_code)] // the highlight overlay only builds Selected / Hover
    None,
    /// Hovered — light orange wash.
    Hover,
    /// Selected — stronger blue wash.
    Selected,
}

impl Highlight {
    /// Blend colour and mix factor, or `None` when the mesh keeps its colour.
    fn tint(self) -> Option<([f32; 4], f32)> {
        match self {
            Highlight::None => None,
            Highlight::Hover => Some(([0.95, 0.55, 0.10, 1.0], 0.35)),
            Highlight::Selected => Some(([0.15, 0.55, 1.0, 1.0], 0.60)),
        }
    }
}

// ── Batched mesh buffers ──────────────────────────────────────────────────
//
// One MeshGpu per solid means one vertex/index bind + draw call per solid —
// ~10k draw calls a frame on a heavy 3D model, which strangles the GPU front
// end. The batch concatenates every solid's LOD0 geometry into a handful of
// large buffers (split only to stay under the 256 MB per-buffer cap), so the
// whole mesh set draws in a few calls. Vertices already carry their own colour,
// so no per-mesh state is needed between draws. Built once per geometry epoch —
// selection/hover no longer rebuild it (that tint is dropped in the batch path).

pub struct MeshBatchChunk {
    pub vertex_buffer: wgpu::Buffer,
    /// Opaque triangle indices (mesh colour alpha ≈ 1). Drawn with depth write.
    pub index_buffer: wgpu::Buffer,
    pub index_count: u32,
    /// Transparent triangle indices (mesh colour alpha < 1). Drawn after the
    /// opaque fills with depth write disabled so they blend over — rather than
    /// erase — the geometry behind them.
    pub transp_index_buffer: wgpu::Buffer,
    pub transp_index_count: u32,
    /// Triangle-edge line list (into `vertex_buffer`) for plain meshes that
    /// carry no B-rep edges — the tessellation wireframe.
    pub wire_index_buffer: wgpu::Buffer,
    pub wire_index_count: u32,
    /// B-rep feature edges of ACIS solids, as a standalone LineList vertex
    /// buffer (pairs of endpoints), drawn non-indexed. Empty for plain meshes.
    pub edge_vertex_buffer: wgpu::Buffer,
    pub edge_vertex_count: u32,
}

fn make_chunk(
    device: &wgpu::Device,
    verts: &[MeshVertex],
    indices: &[u32],
    transp_indices: &[u32],
    wire_indices: &[u32],
    edge_verts: &[MeshVertex],
) -> MeshBatchChunk {
    // `create_buffer_init` with an empty slice yields a zero-sized buffer that
    // some backends reject for INDEX usage; a chunk can legitimately hold only
    // opaque or only transparent tris, so fall back to a 1-index stub (count
    // stays 0, so the draw loop skips it).
    let mk_index = |data: &[u32], label: &'static str| {
        let stub = [0u32];
        let src = if data.is_empty() { &stub[..] } else { data };
        device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some(label),
            contents: bytemuck::cast_slice(src),
            usage: wgpu::BufferUsages::INDEX,
        })
    };
    let mk_vertex = |data: &[MeshVertex], label: &'static str| {
        let stub = [MeshVertex {
            position: [0.0; 3],
            normal: [0.0, 1.0, 0.0],
            color: [0.0; 4],
            position_low: [0.0; 3],
        }];
        let src = if data.is_empty() { &stub[..] } else { data };
        device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some(label),
            contents: bytemuck::cast_slice(src),
            usage: wgpu::BufferUsages::VERTEX,
        })
    };
    MeshBatchChunk {
        vertex_buffer: mk_vertex(verts, "mesh.batch.vbuf"),
        index_buffer: mk_index(indices, "mesh.batch.ibuf"),
        index_count: indices.len() as u32,
        transp_index_buffer: mk_index(transp_indices, "mesh.batch.transp_ibuf"),
        transp_index_count: transp_indices.len() as u32,
        wire_index_buffer: mk_index(wire_indices, "mesh.batch.wire_ibuf"),
        wire_index_count: wire_indices.len() as u32,
        edge_vertex_buffer: mk_vertex(edge_verts, "mesh.batch.edge_vbuf"),
        edge_vertex_count: edge_verts.len() as u32,
    }
}

/// Concatenate every set's first non-empty LOD into a few large GPU buffers.
/// Returns the chunks plus the total triangle count drawn (for diagnostics).
///
/// Every emitted buffer stays under the device's `max_buffer_size` (default
/// 256 MB). Both the vertex buffer (`size_of::<MeshVertex>()` B/vert) and the
/// wire-index buffer (6 u32 = 24 B/triangle — the fattest index buffer) are
/// bounded; a single mesh too large for one chunk is split into triangle-soup
/// sub-chunks so an XREF-heavy model can never overflow a single buffer (#203).
pub fn build_mesh_batch(device: &wgpu::Device, sets: &[MeshLodSet]) -> (Vec<MeshBatchChunk>, u64) {
    // Derive the caps from the real device limit and vertex size. The previous
    // fixed 6 M-vertex cap assumed 40 B/vertex, but `position_low` (RTE) grew
    // MeshVertex to 52 B, so 6 M × 52 B = 312 MB blew past the 256 MB cap.
    let budget = (device.limits().max_buffer_size as usize / 10) * 9; // 10% headroom
    let vsize = std::mem::size_of::<MeshVertex>();
    let max_verts = (budget / vsize).max(3);
    let max_tris = (budget / (6 * 4)).max(1); // wire-index buffer: 6 u32 per tri

    let mut chunks = Vec::new();
    let mut verts: Vec<MeshVertex> = Vec::new();
    let mut indices: Vec<u32> = Vec::new();
    let mut transp_indices: Vec<u32> = Vec::new();
    let mut wire_indices: Vec<u32> = Vec::new();
    let mut edge_verts: Vec<MeshVertex> = Vec::new();
    let mut total_tris = 0u64;
    for set in sets {
        let Some(mesh) = set.lods.iter().find(|m| !m.indices.is_empty()) else {
            continue;
        };
        let has_normals = mesh.normals.len() == mesh.verts.len();
        let vtx = |vi: usize| MeshVertex {
            position: mesh.verts[vi],
            normal: if has_normals { mesh.normals[vi] } else { [0.0, 1.0, 0.0] },
            color: mesh.color,
            position_low: mesh.verts_low.get(vi).copied().unwrap_or([0.0; 3]),
        };
        // A solid whose baked colour is not fully opaque routes into the
        // transparent index stream so it is drawn last, without depth writes.
        let is_transp = mesh.color[3] < 0.999;
        let mesh_tris = mesh.indices.len() / 3;
        total_tris += mesh_tris as u64;

        // Feature edges present (ACIS solid) → emit the B-rep edges as a line
        // list and skip the triangulation wireframe. Absent (plain mesh) → keep
        // the triangle edges so the mesh still shows a wireframe.
        let has_feat = !set.edge_verts.is_empty();
        if has_feat {
            for i in 0..set.edge_verts.len() {
                edge_verts.push(MeshVertex {
                    position: set.edge_verts[i],
                    normal: [0.0, 1.0, 0.0],
                    color: mesh.color,
                    position_low: set.edge_verts_low.get(i).copied().unwrap_or([0.0; 3]),
                });
            }
        }

        // A single mesh larger than a whole chunk: emit as triangle-soup
        // sub-chunks (corners expanded, no vertex sharing) so each buffer fits.
        if mesh.verts.len() > max_verts || mesh_tris > max_tris {
            if !verts.is_empty() || !edge_verts.is_empty() {
                chunks.push(make_chunk(
                    device,
                    &verts,
                    &indices,
                    &transp_indices,
                    &wire_indices,
                    &edge_verts,
                ));
                verts.clear();
                indices.clear();
                transp_indices.clear();
                wire_indices.clear();
                edge_verts.clear();
            }
            let tris_per = (max_verts / 3).min(max_tris).max(1);
            let mut t = 0;
            while t < mesh_tris {
                let end = (t + tris_per).min(mesh_tris);
                let (mut sv, mut si, mut swi) = (Vec::new(), Vec::new(), Vec::new());
                for tri in t..end {
                    let ix = &mesh.indices[tri * 3..tri * 3 + 3];
                    let b = sv.len() as u32;
                    sv.push(vtx(ix[0] as usize));
                    sv.push(vtx(ix[1] as usize));
                    sv.push(vtx(ix[2] as usize));
                    si.extend_from_slice(&[b, b + 1, b + 2]);
                    if !has_feat {
                        swi.extend_from_slice(&[b, b + 1, b + 1, b + 2, b + 2, b]);
                    }
                }
                // The whole mesh shares one colour, so a sub-chunk is entirely
                // opaque or entirely transparent.
                if is_transp {
                    chunks.push(make_chunk(device, &sv, &[], &si, &swi, &[]));
                } else {
                    chunks.push(make_chunk(device, &sv, &si, &[], &swi, &[]));
                }
                t = end;
            }
            continue;
        }

        // Flush when adding this mesh would overflow either the vertex buffer
        // or the wire-index buffer.
        if !verts.is_empty()
            && (verts.len() + mesh.verts.len() > max_verts
                || wire_indices.len() / 6 + mesh_tris > max_tris)
        {
            chunks.push(make_chunk(
                device,
                &verts,
                &indices,
                &transp_indices,
                &wire_indices,
                &edge_verts,
            ));
            verts.clear();
            indices.clear();
            transp_indices.clear();
            wire_indices.clear();
            edge_verts.clear();
        }
        let base = verts.len() as u32;
        for i in 0..mesh.verts.len() {
            verts.push(vtx(i));
        }
        let fill = if is_transp { &mut transp_indices } else { &mut indices };
        for &idx in &mesh.indices {
            fill.push(base + idx);
        }
        if !has_feat {
            for tri in mesh.indices.chunks_exact(3) {
                let (a, b, c) = (base + tri[0], base + tri[1], base + tri[2]);
                wire_indices.extend_from_slice(&[a, b, b, c, c, a]);
            }
        }
    }
    if !indices.is_empty() || !transp_indices.is_empty() || !edge_verts.is_empty() {
        chunks.push(make_chunk(
            device,
            &verts,
            &indices,
            &transp_indices,
            &wire_indices,
            &edge_verts,
        ));
    }
    (chunks, total_tris)
}

impl MeshLodGpu {
    #[allow(dead_code)] // built by the bypassed per-mesh upload_meshes path
    pub fn new(device: &wgpu::Device, set: &MeshLodSet, highlight: Highlight) -> Self {
        Self {
            lods: set
                .lods
                .iter()
                .filter(|m| !m.indices.is_empty())
                .map(|m| MeshGpu::new(device, m, highlight))
                .collect(),
            world_aabb: set.world_aabb,
        }
    }
}

impl MeshGpu {
    pub fn new(device: &wgpu::Device, mesh: &MeshModel, highlight: Highlight) -> Self {
        let has_normals = mesh.normals.len() == mesh.verts.len();
        // Blend the base colour toward the highlight so a selected / hovered
        // solid reads clearly while keeping some shape shading.
        let color = match highlight.tint() {
            Some((hl, t)) => {
                let mut c = [0.0f32; 4];
                for k in 0..4 {
                    c[k] = mesh.color[k] * (1.0 - t) + hl[k] * t;
                }
                c
            }
            None => mesh.color,
        };
        let vertices: Vec<MeshVertex> = mesh
            .verts
            .iter()
            .enumerate()
            .map(|(i, &pos)| {
                let normal = if has_normals {
                    mesh.normals[i]
                } else {
                    [0.0, 1.0, 0.0]
                };
                MeshVertex {
                    position: pos,
                    normal,
                    color,
                    position_low: mesh.verts_low.get(i).copied().unwrap_or([0.0; 3]),
                }
            })
            .collect();

        let vertex_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some(&format!("mesh.vbuf.{}", mesh.name)),
            contents: bytemuck::cast_slice(&vertices),
            usage: wgpu::BufferUsages::VERTEX,
        });

        let index_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some(&format!("mesh.ibuf.{}", mesh.name)),
            contents: bytemuck::cast_slice(&mesh.indices),
            usage: wgpu::BufferUsages::INDEX,
        });

        // Wireframe-mode index buffer: expand each triangle into its
        // three edge segments. Allocates ~2× the solid index count but
        // is cheap compared to mesh tessellation and only happens when
        // a new mesh is uploaded.
        let mut wire_indices: Vec<u32> = Vec::with_capacity(mesh.indices.len() * 2);
        for tri in mesh.indices.chunks_exact(3) {
            let (a, b, c) = (tri[0], tri[1], tri[2]);
            wire_indices.extend_from_slice(&[a, b, b, c, c, a]);
        }
        let wire_index_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some(&format!("mesh.wire_ibuf.{}", mesh.name)),
            contents: bytemuck::cast_slice(&wire_indices),
            usage: wgpu::BufferUsages::INDEX,
        });

        Self {
            vertex_buffer,
            index_buffer,
            index_count: mesh.indices.len() as u32,
            wire_index_buffer,
            wire_index_count: wire_indices.len() as u32,
        }
    }
}
