// DATALINK command — manages data links to external spreadsheets.

use crate::modules::{IconKind, ModuleEvent, ToolDef};

pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/data_link.svg"));

pub fn tool() -> ToolDef {
    ToolDef {
        id: "DATALINK",
        label: "Link\nData",
        icon: ICON,
        event: ModuleEvent::Command("DATALINK".to_string()),
    }
}
