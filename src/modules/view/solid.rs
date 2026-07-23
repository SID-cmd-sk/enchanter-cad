// Solid (Shaded) visual style toggle.
// id "SOLID" is special-cased in ribbon.rs for active-state highlighting.

use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/solid.svg"));
pub fn tool() -> ToolDef {
    ToolDef {
        id: "SOLID",
        label: "Solid",
        icon: ICON,
        event: ModuleEvent::SetWireframe(false),
    }
}
