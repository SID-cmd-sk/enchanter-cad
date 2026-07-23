//! Polar-tracking angle picker — sets the polar increment used by POLAR
//! tracking. Rendered as a floating overlay above the status bar, same pattern
//! as the units / scale pickers. Offers the common AutoCAD-style increments
//! plus a free-text field for any custom angle (#264).

use iced::widget::{button, column, container, mouse_area, row, text, text_input};
use iced::{Background, Border, Color, Element, Fill, Length, Rectangle, Theme};

use crate::app::Message;

/// Angle increments offered in the picker, in degrees. Matches the common
/// drafting set and adds the fine 1° step requested in #264.
const PRESETS: &[f32] = &[90.0, 45.0, 30.0, 22.5, 18.0, 15.0, 10.0, 5.0, 1.0];

/// Format an angle without a trailing `.0` (so `22.5°` but `15°`).
pub fn angle_label(deg: f32) -> String {
    if (deg.fract()).abs() < 1e-3 {
        format!("{:.0}°", deg)
    } else {
        format!("{deg}°")
    }
}

/// Full-screen overlay: transparent click-catcher + angle list pinned
/// bottom-right, above the status bar. `custom` is the live text of the
/// free-entry field.
pub fn polar_popup_overlay<'a>(
    current: f32,
    custom: &'a str,
    pill: Option<Rectangle>,
    win: (f32, f32),
) -> Element<'a, Message> {
    let mut rows: Vec<Element<'a, Message>> = PRESETS
        .iter()
        .map(|&deg| {
            let active = (current - deg).abs() < 1e-3;
            angle_row(deg, active)
        })
        .collect();

    // Free-entry custom angle: type a value and press Enter to apply.
    let custom_field = text_input("Custom…", custom)
        .on_input(Message::PolarCustomInput)
        .on_submit(Message::SubmitPolarCustom)
        .size(11)
        .padding([2, 6])
        .width(Length::Fixed(58.0));
    let custom_row = container(
        row![
            custom_field,
            text("°").size(11).color(LABEL_OFF),
        ]
        .spacing(4)
        .align_y(iced::Center),
    )
    .padding([5, 10]);
    rows.push(custom_row.into());

    let panel = container(column(rows))
        .style(|_: &Theme| container::Style {
            background: Some(Background::Color(PANEL_BG)),
            border: Border {
                color: PANEL_BORDER,
                width: 1.0,
                radius: 3.0.into(),
            },
            ..Default::default()
        })
        .width(Length::Fixed(120.0));

    let positioned = super::position_statusbar_popup(panel.into(), pill, win, 120.0, true);

    mouse_area(positioned)
        .on_press(Message::ClosePolarPopup)
        .into()
}

fn angle_row<'a>(deg: f32, active: bool) -> Element<'a, Message> {
    let check = crate::ui::icons::check_cell(active, CHECK_COLOR);

    let lbl = text(angle_label(deg))
        .size(11)
        .color(if active { LABEL_ON } else { LABEL_OFF });

    let content = row![check, lbl].spacing(6).align_y(iced::Center);

    button(content)
        .on_press(Message::SetPolarAngle(deg))
        .style(|_: &Theme, status| button::Style {
            background: Some(Background::Color(match status {
                button::Status::Hovered => ROW_HOVER,
                _ => Color::TRANSPARENT,
            })),
            ..Default::default()
        })
        .width(Fill)
        .padding([4, 10])
        .into()
}

// ── Colours ───────────────────────────────────────────────────────────────

const PANEL_BG: Color = Color {
    r: 0.15,
    g: 0.15,
    b: 0.15,
    a: 1.0,
};
const PANEL_BORDER: Color = Color {
    r: 0.32,
    g: 0.32,
    b: 0.32,
    a: 1.0,
};
const ROW_HOVER: Color = Color {
    r: 0.22,
    g: 0.22,
    b: 0.22,
    a: 1.0,
};
const CHECK_COLOR: Color = Color {
    r: 0.35,
    g: 0.75,
    b: 1.00,
    a: 1.0,
};
const LABEL_ON: Color = Color {
    r: 0.92,
    g: 0.92,
    b: 0.92,
    a: 1.0,
};
const LABEL_OFF: Color = Color {
    r: 0.65,
    g: 0.65,
    b: 0.65,
    a: 1.0,
};
