use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/pc_attach.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "POINTCLOUDATTACH",
        label: "Attach",
        icon: ICON,
        event: ModuleEvent::Command("POINTCLOUDATTACH".to_string()),
    }
}
