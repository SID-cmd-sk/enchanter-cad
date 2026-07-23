use crate::modules::{IconKind, ModuleEvent, ToolDef};
pub fn tool() -> ToolDef {
    ToolDef {
        id: "OPEN",
        label: "Open",
        icon: IconKind::Svg(include_bytes!("../../../assets/icons/import_obj.svg")),
        event: ModuleEvent::OpenFileDialog,
    }
}
