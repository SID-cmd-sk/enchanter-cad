use super::*;
use super::super::document::{DynComponent, DynFieldEntry};
use super::super::Message;
use iced::widget::{
    button, container, mouse_area, row,
};
use iced::{Background, Border, Color, Element, Theme};

pub(super) fn viewport_controls<'a>(
    render_mode: acadrust::entities::ViewportRenderMode,
    show_grid: bool,
    snap_on: bool,
    include_split: bool,
    tile_count: usize,
) -> Element<'a, Message> {
    use acadrust::entities::ViewportRenderMode as M;
    let render_modes: Vec<RenderModeChoice> = vec![
        RenderModeChoice(M::Wireframe2D),
        RenderModeChoice(M::Wireframe3D),
        RenderModeChoice(M::HiddenLine),
        RenderModeChoice(M::FlatShaded),
        RenderModeChoice(M::GouraudShaded),
        RenderModeChoice(M::FlatShadedWithEdges),
        RenderModeChoice(M::GouraudShadedWithEdges),
    ];
    let light = Color { r: 0.85, g: 0.85, b: 0.85, a: 1.0 };
    let accent = Color { r: 0.45, g: 0.70, b: 1.0, a: 1.0 };
    let green = Color { r: 0.36, g: 0.80, b: 0.45, a: 1.0 };
    let red = Color { r: 0.92, g: 0.38, b: 0.38, a: 1.0 };

    // Fixed-colour icon button (close = red); colour stays on hover.
    let tinted_btn = move |bytes: &'static [u8], color: Color, msg: Message| {
        button(crate::ui::icons::tinted(bytes, 15.0, color))
            .on_press(msg)
            .padding([4, 6])
            .style(move |_: &Theme, status| iced::widget::button::Style {
                background: Some(Background::Color(match status {
                    iced::widget::button::Status::Hovered
                    | iced::widget::button::Status::Pressed => Color {
                        r: 0.25,
                        g: 0.25,
                        b: 0.25,
                        a: 0.9,
                    },
                    _ => Color::TRANSPARENT,
                })),
                border: Border {
                    radius: 3.0.into(),
                    ..Default::default()
                },
                text_color: color,
                ..Default::default()
            })
    };

    // Borderless icon button; an `active` toggle gets an accent tint + fill.
    let icon_btn = move |bytes: &'static [u8], active: bool, msg: Message| {
        let tint = if active { accent } else { light };
        button(crate::ui::icons::tinted(bytes, 15.0, tint))
            .on_press(msg)
            .padding([4, 6])
            .style(move |_: &Theme, status| iced::widget::button::Style {
                background: Some(Background::Color(match (active, status) {
                    (_, iced::widget::button::Status::Hovered) => Color {
                        r: 0.25,
                        g: 0.25,
                        b: 0.25,
                        a: 0.9,
                    },
                    (true, _) => Color {
                        r: 0.16,
                        g: 0.22,
                        b: 0.32,
                        a: 0.9,
                    },
                    (false, _) => Color::TRANSPARENT,
                })),
                border: Border {
                    radius: 3.0.into(),
                    ..Default::default()
                },
                text_color: tint,
                ..Default::default()
            })
    };

    // Render-mode picker, restyled borderless so the outer chip frames it.
    let picker = iced::widget::pick_list(
        render_modes,
        Some(RenderModeChoice(render_mode)),
        |c| Message::SetRenderMode(c.0),
    )
    .text_size(11)
    .padding([4, 6])
    .style(move |_: &Theme, _| iced::widget::pick_list::Style {
        background: Background::Color(Color::TRANSPARENT),
        border: Border {
            radius: 3.0.into(),
            ..Default::default()
        },
        text_color: light,
        placeholder_color: light,
        handle_color: light,
    });

    // Thin vertical divider between control groups.
    let sep = || {
        container(iced::widget::Space::new().width(1.0).height(16.0)).style(|_: &Theme| {
            iced::widget::container::Style {
                background: Some(Background::Color(Color {
                    r: 0.45,
                    g: 0.45,
                    b: 0.45,
                    a: 0.7,
                })),
                ..Default::default()
            }
        })
    };

    let mut bar = row![]
        .spacing(3)
        .align_y(iced::alignment::Vertical::Center);
    bar = bar
        .push(icon_btn(crate::ui::icons::GRID, show_grid, Message::ToggleGrid))
        .push(sep())
        .push(icon_btn(crate::ui::icons::SNAP, snap_on, Message::ToggleGridSnap))
        .push(sep())
        .push(picker);
    if include_split {
        bar = bar
            .push(sep())
            .push(icon_btn(crate::ui::icons::SPLIT_V, false, Message::SplitModelViewport(false)))
            .push(sep())
            .push(icon_btn(crate::ui::icons::SPLIT_H, false, Message::SplitModelViewport(true)));
        // Drag handle + close: only meaningful with more than one model tile.
        // The handle is a `mouse_area` (not a button) so it fires on press-DOWN,
        // letting the drag continue onto the target pane to swap them (a button
        // would only fire on release). Placed just left of Close.
        if tile_count > 1 {
            let drag = mouse_area(
                container(crate::ui::icons::tinted(crate::ui::icons::MOVE, 15.0, green))
                    .padding([4, 6])
                    .style(|_: &Theme| iced::widget::container::Style {
                        border: Border {
                            radius: 3.0.into(),
                            ..Default::default()
                        },
                        ..Default::default()
                    }),
            )
            .interaction(iced::mouse::Interaction::Grab)
            .on_press(Message::PaneMoveStart);
            bar = bar
                .push(sep())
                .push(drag)
                .push(sep())
                .push(tinted_btn(crate::ui::icons::CLOSE, red, Message::CloseModelViewport));
        }
    }

    container(bar)
        .padding(2)
        .style(|_: &Theme| iced::widget::container::Style {
            background: Some(Background::Color(Color {
                r: 0.10,
                g: 0.10,
                b: 0.10,
                a: 0.75,
            })),
            border: Border {
                color: Color {
                    r: 0.35,
                    g: 0.35,
                    b: 0.35,
                    a: 1.0,
                },
                width: 1.0,
                radius: 4.0.into(),
            },
            ..Default::default()
        })
        .into()
}

// ── Dynamic-input field formatting ─────────────────────────────────────────

/// Short prefix shown before a dynamic-input box's value.
/// The string shown inside a dynamic-input box: the typed buffer when the
/// field is locked, otherwise the live value derived from the cursor
/// world position (and the base point for polar quantities).
pub(super) fn dyn_component_value(
    f: &DynFieldEntry,
    w: glam::DVec3,
    base: Option<glam::DVec3>,
    xf: &super::super::helpers::UcsXform,
    comma_cartesian: bool,
) -> String {
    if let Some(b) = &f.buffer {
        return b.clone();
    }
    let b = base.unwrap_or(glam::DVec3::ZERO);
    // Relative deltas and the polar angle read in the active UCS plane. The
    // delta is offset-invariant, so only the axis rotation matters (identity
    // xf reproduces the world-frame deltas).
    let d = xf.vec_to_ucs(w - b);
    let dx = d.x as f64;
    let dy = d.y as f64;
    // When a base point exists (DYN-on after the first pick) the cartesian
    // fields show relative deltas — matching the typed-value convention
    // in `dyn_resolve_point` so the live preview and the committed
    // coordinate use the same frame. See #35.
    let has_base = base.is_some();
    // Width / Height read as unsigned magnitudes (the sign is taken from the
    // cursor side on commit), matching the rectangle's two-edge entry. But once
    // the user separates the values with `,` the entry is a cartesian
    // coordinate pair, so the fields read as signed X/Y deltas to match the
    // committed point (#269).
    let wh = matches!(f.role, crate::command::DynRole::Width | crate::command::DynRole::Height)
        && !comma_cartesian;
    match f.component {
        DynComponent::X if has_base => format!("{:.4}", if wh { dx.abs() } else { dx }),
        DynComponent::Y if has_base => format!("{:.4}", if wh { dy.abs() } else { dy }),
        DynComponent::Z if has_base => "0.0000".to_string(),
        DynComponent::X => format!("{:.4}", w.x),
        DynComponent::Y => format!("{:.4}", w.y),
        DynComponent::Z => format!("{:.4}", b.z),
        // Scaled by the role so a diameter box reads twice the radius.
        DynComponent::Distance => {
            format!("{:.4}", (dx * dx + dy * dy).sqrt() * f.role.value_scale() as f64)
        }
        // Shared rule: unsigned magnitude of the short angle, so CW (below the
        // reference axis) reads positive (e.g. 30°, not -30°/330°). The
        // committed value stays signed (see dyn_resolve_point).
        DynComponent::Angle => {
            format!("{:.1}", crate::command::dyn_display_angle_deg(dy.atan2(dx) as f32))
        }
        // Typed-only scalar — no geometric value to track when empty.
        DynComponent::Scalar => String::new(),
    }
}
