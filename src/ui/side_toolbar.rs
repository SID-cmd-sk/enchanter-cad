//! Reusable right-edge vertical toolbar.
//!
//! A single centred column of icon buttons floated over the right edge of the
//! canvas — a lightweight, context-specific alternative to a contextual ribbon
//! tab. It is built from a flat list of [`ToolDef`]s and dispatches each tool's
//! command through the existing [`Message::RibbonToolClick`] path, so any
//! module's tools can drive it. First used for paper-space viewport / plot
//! actions; reusable for any future context action set.

use iced::widget::{button, column, container, svg, text, tooltip};
use iced::{Background, Border, Color, Element, Length, Theme};

use crate::app::Message;
use crate::modules::{IconKind, ToolDef};

const PANEL_BG: Color = Color { r: 0.13, g: 0.13, b: 0.13, a: 0.96 };
const PANEL_BORDER: Color = Color { r: 0.32, g: 0.32, b: 0.32, a: 1.0 };
const BTN_HOVER: Color = Color { r: 0.24, g: 0.24, b: 0.24, a: 1.0 };
const ICON_SIZE: f32 = 22.0;
const BTN_SIZE: f32 = 38.0;
/// Gap between the toolbar and the right edge of the canvas.
const EDGE_MARGIN: f32 = 8.0;

fn icon_el(icon: IconKind) -> Element<'static, Message> {
    match icon {
        IconKind::Glyph(s) => text(s).size(ICON_SIZE * 0.85).color(Color::WHITE).into(),
        IconKind::Svg(bytes) => svg(svg::Handle::from_memory(bytes))
            .width(Length::Fixed(ICON_SIZE))
            .height(Length::Fixed(ICON_SIZE))
            .into(),
    }
}

fn tip_panel(label: &'static str) -> Element<'static, Message> {
    container(text(label).size(11).color(Color::WHITE))
        .padding([2, 6])
        .style(|_: &Theme| container::Style {
            background: Some(Background::Color(PANEL_BG)),
            border: Border {
                color: PANEL_BORDER,
                width: 1.0,
                radius: 3.0.into(),
            },
            ..Default::default()
        })
        .into()
}

/// Build the floating right-edge vertical toolbar from `tools`, vertically
/// centred over the canvas. Returns `None` when `tools` is empty so the caller
/// can skip pushing an overlay.
pub fn view(tools: &[ToolDef]) -> Option<Element<'static, Message>> {
    if tools.is_empty() {
        return None;
    }

    let mut col = column![].spacing(4).align_x(iced::Center);
    for t in tools {
        let btn = button(icon_el(t.icon))
            .on_press(Message::RibbonToolClick {
                tool_id: t.id.to_string(),
                event: t.event.clone(),
            })
            .width(Length::Fixed(BTN_SIZE))
            .height(Length::Fixed(BTN_SIZE))
            .style(|_: &Theme, status| button::Style {
                background: Some(Background::Color(match status {
                    button::Status::Hovered | button::Status::Pressed => BTN_HOVER,
                    _ => Color::TRANSPARENT,
                })),
                border: Border {
                    radius: 3.0.into(),
                    ..Default::default()
                },
                text_color: Color::WHITE,
                ..Default::default()
            });
        // Label tooltip on the left so it never runs off the right edge.
        col = col.push(
            tooltip(btn, tip_panel(t.label), tooltip::Position::Left).gap(6),
        );
    }

    let panel = container(col).padding(4).style(|_: &Theme| container::Style {
        background: Some(Background::Color(PANEL_BG)),
        border: Border {
            color: PANEL_BORDER,
            width: 1.0,
            radius: 5.0.into(),
        },
        ..Default::default()
    });

    // Fill the canvas, pin the panel to the right edge and centre it
    // vertically — no manual size/position math needed.
    Some(
        container(iced::widget::opaque(panel))
            .width(Length::Fill)
            .height(Length::Fill)
            .align_x(iced::Right)
            .align_y(iced::Center)
            .padding(iced::Padding {
                right: EDGE_MARGIN,
                ..iced::Padding::ZERO
            })
            .into(),
    )
}
