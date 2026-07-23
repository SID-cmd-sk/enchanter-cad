//! Consolidated user configuration — one grouped JSON file
//! (`<config>/OpenCADStudio/settings.json`) holding every app preference except
//! the command aliases (which stay in the hand-editable `ocad.pgp`). Serialized
//! via serde so the file is structured and grouped, replacing the former
//! scattered flat stores (`settings.txt` / `recent.txt` / `recent_limit.txt` /
//! `statusbar.txt` / `ribbon.txt` / `plot.txt`).

use serde::{Deserialize, Serialize};

use super::settings::UserSettings;
use crate::ui::ribbon::CollapseMode;
use crate::ui::statusbar::statusbar_config::StatusBarConfig;
use crate::ui::window::plot::PlotDialogState;

/// The whole persisted config, grouped into top-level sections.
#[derive(Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AppConfig {
    /// Input modes, backup, plugin lists, viewport background colours, …
    pub settings: UserSettings,
    /// Recent-files list + retained count.
    pub recent: RecentConfig,
    /// Which status-bar pills the user has hidden.
    pub statusbar: StatusBarConfig,
    /// Ribbon collapse density.
    pub ribbon: RibbonConfig,
    /// Print dialog preferences (only the persisted fields; runtime state is
    /// skipped by `PlotDialogState`'s serde attributes).
    pub plot: PlotDialogState,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            settings: UserSettings::default(),
            recent: RecentConfig::default(),
            statusbar: StatusBarConfig::default(),
            ribbon: RibbonConfig::default(),
            plot: PlotDialogState::default(),
        }
    }
}

#[derive(Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct RecentConfig {
    /// Recently opened file paths, newest first.
    pub files: Vec<String>,
    /// How many recent files to keep.
    pub limit: usize,
}

impl Default for RecentConfig {
    fn default() -> Self {
        Self {
            files: Vec::new(),
            limit: super::recent::RECENT_DEFAULT,
        }
    }
}

#[derive(Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct RibbonConfig {
    pub collapse: CollapseMode,
}

impl AppConfig {
    /// Read the saved config, or all-defaults when the file is missing or
    /// unreadable (fresh install / wasm). Unknown or missing fields fall back to
    /// their section defaults via `#[serde(default)]`.
    pub fn load() -> Self {
        config_path()
            .and_then(|p| std::fs::read_to_string(p).ok())
            .and_then(|body| serde_json::from_str(&body).ok())
            .unwrap_or_default()
    }

    /// Persist the config as pretty JSON. Best-effort; silent on failure
    /// (read-only home, full disk, wasm — where `config_dir` is `None`).
    pub fn save(&self) {
        let Some(path) = config_path() else { return };
        if let Some(dir) = path.parent() {
            let _ = std::fs::create_dir_all(dir);
        }
        if let Ok(json) = serde_json::to_string_pretty(self) {
            let _ = std::fs::write(path, json);
        }
    }
}

fn config_path() -> Option<std::path::PathBuf> {
    Some(crate::config::config_dir()?.join("settings.json"))
}
