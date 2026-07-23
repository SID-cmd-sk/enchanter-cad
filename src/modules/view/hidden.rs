use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/hidden.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "HIDDENLINE",
        label: "Hidden",
        icon: ICON,
        event: ModuleEvent::Command("HIDDENLINE".to_string()),
    }
}
