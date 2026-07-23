use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/xadjust.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "ADJUST",
        label: "Adjust",
        icon: ICON,
        event: ModuleEvent::Command("ADJUST".to_string()),
    }
}
