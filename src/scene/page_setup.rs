//! Named page setups — the reusable plot configurations a drawing stores in
//! its `ACAD_PLOTSETTINGS` dictionary (each a standalone `PlotSettings` object
//! keyed by name). These are distinct from a layout's own embedded plot
//! settings: a named setup can be applied to any layout. CRUD here keeps the
//! dictionary + objects consistent so the result round-trips through DWG/DXF.

use super::Scene;
use acadrust::objects::{Dictionary, ObjectType, PlotSettings};
use acadrust::Handle;

impl Scene {
    /// Names of the document's named page setups, in dictionary order.
    pub fn page_setup_names(&self) -> Vec<String> {
        let dh = self.document.header.acad_plotsettings_dict_handle;
        match self.document.objects.get(&dh) {
            Some(ObjectType::Dictionary(d)) => d.entries.iter().map(|(k, _)| k.clone()).collect(),
            _ => Vec::new(),
        }
    }

    /// Clone the named page setup's `PlotSettings`, or `None` if absent.
    pub fn page_setup_get(&self, name: &str) -> Option<PlotSettings> {
        let dh = self.document.header.acad_plotsettings_dict_handle;
        let ObjectType::Dictionary(d) = self.document.objects.get(&dh)? else {
            return None;
        };
        let h = d.entries.iter().find(|(k, _)| k == name).map(|(_, h)| *h)?;
        match self.document.objects.get(&h)? {
            ObjectType::PlotSettings(ps) => Some(ps.clone()),
            _ => None,
        }
    }

    /// Handle of the `ACAD_PLOTSETTINGS` dictionary, creating it (and its entry
    /// in the root named-objects dictionary) if the drawing has none yet.
    fn ensure_plotsettings_dict(&mut self) -> Handle {
        let dh = self.document.header.acad_plotsettings_dict_handle;
        if matches!(self.document.objects.get(&dh), Some(ObjectType::Dictionary(_))) {
            return dh;
        }
        let root = self.document.header.named_objects_dict_handle;
        let mut dict = Dictionary::new();
        dict.handle = self.document.allocate_handle();
        dict.owner = root;
        let new_handle = dict.handle;
        self.document
            .objects
            .insert(new_handle, ObjectType::Dictionary(dict));
        self.document.header.acad_plotsettings_dict_handle = new_handle;
        if let Some(ObjectType::Dictionary(rd)) = self.document.objects.get_mut(&root) {
            rd.entries.retain(|(k, _)| k != "ACAD_PLOTSETTINGS");
            rd.entries.push(("ACAD_PLOTSETTINGS".to_string(), new_handle));
        }
        new_handle
    }

    /// Handle of the named page setup, if it exists.
    fn page_setup_handle(&self, name: &str) -> Option<Handle> {
        let dh = self.document.header.acad_plotsettings_dict_handle;
        let ObjectType::Dictionary(d) = self.document.objects.get(&dh)? else {
            return None;
        };
        d.entries.iter().find(|(k, _)| k == name).map(|(_, h)| *h)
    }

    /// Create or update the named page setup from `ps` (its `page_name` and
    /// `owner` are set here). Existing entries are updated in place; new ones
    /// are inserted and registered in the dictionary.
    pub fn page_setup_save(&mut self, name: &str, mut ps: PlotSettings) {
        let dict_handle = self.ensure_plotsettings_dict();
        ps.page_name = name.to_string();
        ps.owner = dict_handle;
        if let Some(h) = self.page_setup_handle(name) {
            ps.handle = h;
            self.document.objects.insert(h, ObjectType::PlotSettings(ps));
        } else {
            ps.handle = self.document.allocate_handle();
            let h = ps.handle;
            self.document.objects.insert(h, ObjectType::PlotSettings(ps));
            if let Some(ObjectType::Dictionary(d)) = self.document.objects.get_mut(&dict_handle) {
                d.entries.push((name.to_string(), h));
            }
        }
    }

    /// Remove the named page setup (object + dictionary entry). No-op if absent.
    pub fn page_setup_delete(&mut self, name: &str) {
        let dict_handle = self.document.header.acad_plotsettings_dict_handle;
        let handle = if let Some(ObjectType::Dictionary(d)) =
            self.document.objects.get_mut(&dict_handle)
        {
            let h = d.entries.iter().find(|(k, _)| k == name).map(|(_, h)| *h);
            d.entries.retain(|(k, _)| k != name);
            h
        } else {
            None
        };
        if let Some(h) = handle {
            self.document.objects.remove(&h);
        }
    }

    /// Rename a named page setup (dictionary key + the object's `page_name`).
    /// No-op if `old` is absent or `new` already exists.
    pub fn page_setup_rename(&mut self, old: &str, new: &str) {
        if old == new || new.trim().is_empty() {
            return;
        }
        if self.page_setup_handle(new).is_some() {
            return; // name collision
        }
        let dict_handle = self.document.header.acad_plotsettings_dict_handle;
        let mut renamed = None;
        if let Some(ObjectType::Dictionary(d)) = self.document.objects.get_mut(&dict_handle) {
            if let Some(e) = d.entries.iter_mut().find(|(k, _)| k == old) {
                e.0 = new.to_string();
                renamed = Some(e.1);
            }
        }
        if let Some(h) = renamed {
            if let Some(ObjectType::PlotSettings(ps)) = self.document.objects.get_mut(&h) {
                ps.page_name = new.to_string();
            }
        }
    }
}
