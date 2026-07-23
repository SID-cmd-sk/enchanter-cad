// DATAEXTRACTION command — launches the Data Extraction wizard.

use crate::modules::{IconKind, ModuleEvent, ToolDef};

pub const ICON: IconKind = IconKind::Svg(include_bytes!("../../../assets/icons/data_extract.svg"));

pub fn tool() -> ToolDef {
    ToolDef {
        id: "DATAEXTRACTION",
        label: "Extract\nData",
        icon: ICON,
        event: ModuleEvent::Command("DATAEXTRACTION".to_string()),
    }
}
