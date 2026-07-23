//! Per-object dimension-variable overrides.
//!
//! A leader (or dimension) that departs from its dimension style stores the
//! changed variables in the standard `ACAD_DSTYLE` XDATA record as a list of
//! (dimvar group code, value) pairs wrapped in `{ }` control strings. Both the
//! renderer and the properties panel prefer an override over the style default,
//! so editing one of these rows writes here and the change round-trips to file.

use acadrust::xdata::{ExtendedData, XDataValue};
use acadrust::{CadDocument, Handle};

// DXF group codes of the dimension variables surfaced on the leader panel.
pub const DIMSCALE: i16 = 40; // overall scale       (real)
pub const DIMASZ: i16 = 41; // arrow size          (real)
pub const DIMTAD: i16 = 77; // text vertical pos   (int16)
pub const DIMGAP: i16 = 147; // text offset / gap   (real)
pub const DIMLWD: i16 = 371; // dim line lineweight (int16)
pub const DIMLDRBLK: i16 = 341; // leader arrow block  (handle)

/// Every (code, value) override present in the `ACAD_DSTYLE` record.
pub fn pairs(xd: &ExtendedData) -> Vec<(i16, XDataValue)> {
    let Some(rec) = xd.get_record("ACAD_DSTYLE") else {
        return Vec::new();
    };
    let mut out = Vec::new();
    let mut it = rec.values.iter();
    // The record is a flat stream: a 1070 code marker followed by its typed
    // value, bracketed by 1002 "{" / "}" control strings (which are skipped).
    while let Some(v) = it.next() {
        if let XDataValue::Integer16(code) = v {
            if let Some(val) = it.next() {
                out.push((*code, val.clone()));
            }
        }
    }
    out
}

/// The real-valued override for `code`, if present.
pub fn real(xd: &ExtendedData, code: i16) -> Option<f64> {
    pairs(xd)
        .into_iter()
        .find(|(c, _)| *c == code)
        .and_then(|(_, v)| match v {
            XDataValue::Real(r) | XDataValue::Distance(r) | XDataValue::ScaleFactor(r) => Some(r),
            _ => None,
        })
}

/// The 16-bit-integer override for `code`, if present.
pub fn int(xd: &ExtendedData, code: i16) -> Option<i16> {
    pairs(xd)
        .into_iter()
        .find(|(c, _)| *c == code)
        .and_then(|(_, v)| match v {
            XDataValue::Integer16(n) => Some(n),
            _ => None,
        })
}

/// The handle-valued override for `code`, if present.
pub fn handle(xd: &ExtendedData, code: i16) -> Option<Handle> {
    pairs(xd)
        .into_iter()
        .find(|(c, _)| *c == code)
        .and_then(|(_, v)| match v {
            XDataValue::Handle(h) => Some(h),
            _ => None,
        })
}

/// Set — or, with `value: None`, clear — a single override on entity `handle`,
/// leaving the other overrides in the record untouched. Clearing the last one
/// drops the whole `ACAD_DSTYLE` record.
pub fn set(doc: &mut CadDocument, handle: Handle, code: i16, value: Option<XDataValue>) {
    let Some(entity) = doc.get_entity(handle) else {
        return;
    };
    let mut kept: Vec<(i16, XDataValue)> = pairs(&entity.common().extended_data)
        .into_iter()
        .filter(|(c, _)| *c != code)
        .collect();
    if let Some(v) = value {
        kept.push((code, v));
    }
    let values = if kept.is_empty() {
        None
    } else {
        let mut vals = vec![XDataValue::ControlString("{".to_string())];
        for (c, v) in kept {
            vals.push(XDataValue::Integer16(c));
            vals.push(v);
        }
        vals.push(XDataValue::ControlString("}".to_string()));
        Some(vals)
    };
    crate::scene::view::dispatch::set_entity_xdata(doc, handle, "ACAD_DSTYLE", values);
}
