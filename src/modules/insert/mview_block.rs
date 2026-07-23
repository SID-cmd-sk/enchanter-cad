use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/mview_block.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "BLOCKPALETTE",
        label: "Multi-View\nBlock",
        icon: ICON,
        event: ModuleEvent::Command("BLOCKPALETTE".to_string()),
    }
}
