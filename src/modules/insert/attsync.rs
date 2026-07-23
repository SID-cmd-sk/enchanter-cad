use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/attsync.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "ATTSYNC",
        label: "Synchronize",
        icon: ICON,
        event: ModuleEvent::Command("ATTSYNC".to_string()),
    }
}
