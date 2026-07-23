use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/landxml.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "LANDXMLIMPORT",
        label: "Land\nXML",
        icon: ICON,
        event: ModuleEvent::Command("LANDXMLIMPORT".to_string()),
    }
}
