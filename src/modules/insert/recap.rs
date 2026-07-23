use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/recap.svg"));
pub fn tool() -> ToolDef {
    ToolDef { id: "RECAP", label: "Autodesk\nReCap", icon: ICON, event: ModuleEvent::Command("RECAP".to_string()) }
}
