use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind =
    IconKind::Svg(include_bytes!("../../../assets/icons/snap_underlays.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "UOSNAP",
        label: "Snap to\nUnderlays",
        icon: ICON,
        event: ModuleEvent::Command("UOSNAP".to_string()),
    }
}
