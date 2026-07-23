// Wireframe visual style toggle.
// id "WIREFRAME" is special-cased in ribbon.rs for active-state highlighting.

use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/wireframe.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "WIREFRAME",
        label: "Wireframe",
        icon: ICON,
        event: ModuleEvent::SetWireframe(true),
    }
}
