use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/xray.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "XRAY",
        label: "X-Ray",
        icon: ICON,
        event: ModuleEvent::Command("XRAY".to_string()),
    }
}
