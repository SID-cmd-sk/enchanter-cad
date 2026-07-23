use crate::modules::{IconKind, ModuleEvent, ToolDef};

pub fn tool() -> ToolDef {
    ToolDef {
        id: "LAYOFF",
        label: "Layer Off",
        icon: IconKind::Svg(include_bytes!("../../../../assets/icons/layers/layoff.svg")),
        event: ModuleEvent::Command("LAYOFF".to_string()),
    }
}
