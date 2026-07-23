//! Shared per-user config directory used by the small settings stores (recent
//! files, status-bar layout, ribbon collapse mode, …). Everything lives under
//! `<platform-config>/OpenCADStudio` so the app keeps a single tidy folder.

use std::path::PathBuf;

/// The OpenCADStudio config directory (not created). `None` when the platform
/// config base can't be resolved (e.g. no `HOME`). Callers `join` their own
/// file name onto it and `create_dir_all` its parent before writing.
pub fn config_dir() -> Option<PathBuf> {
    let base: PathBuf = if cfg!(target_os = "windows") {
        std::env::var_os("APPDATA").map(PathBuf::from)?
    } else if cfg!(target_os = "macos") {
        let home = std::env::var_os("HOME")?;
        let mut p = PathBuf::from(home);
        p.push("Library");
        p.push("Application Support");
        p
    } else if let Some(d) = std::env::var_os("XDG_CONFIG_HOME") {
        PathBuf::from(d)
    } else {
        let home = std::env::var_os("HOME")?;
        let mut p = PathBuf::from(home);
        p.push(".config");
        p
    };
    let mut p = base;
    p.push("OpenCADStudio");
    Some(p)
}
