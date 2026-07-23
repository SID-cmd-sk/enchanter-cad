//! Annotation-scale manager — add / delete / edit the drawing's ACAD_SCALELIST.
//!
//! Shares the style managers' frame (toolbar + list + editor + palette) so it
//! looks and behaves like Text / Dim / MLeader style managers, but scales are
//! plain `Scale` objects rather than symbol-table styles, so it drives its own
//! messages instead of the StyleKind machinery.

use crate::app::Message;
use crate::ui::style::style_manager::{hdivider, tb_button, vsep, BG, BORDER, DIM, LIST, TB, TEXT};
use iced::widget::{button, column, container, row, scrollable, text, text_input, Space};
use iced::{Background, Border, Color, Element, Fill, Theme};

const INPUT_BG: Color = Color {
    r: 0.10,
    g: 0.10,
    b: 0.10,
    a: 1.0,
};
const ACTIVE: Color = Color {
    r: 0.20,
    g: 0.40,
    b: 0.70,
    a: 1.0,
};
const CURRENT_CHECK: Color = Color {
    r: 0.30,
    g: 0.82,
    b: 0.36,
    a: 1.0,
};

fn field_style(_: &Theme, _: text_input::Status) -> text_input::Style {
    text_input::Style {
        background: Background::Color(INPUT_BG),
        border: Border {
            color: BORDER,
            width: 1.0,
            radius: 4.0.into(),
        },
        icon: TEXT,
        placeholder: DIM,
        value: TEXT,
        selection: Color {
            r: 0.20,
            g: 0.46,
            b: 0.80,
            a: 0.45,
        },
    }
}

/// `scales` is (name, "paper:drawing" ratio label). The editor buffers hold the
/// name / paper / drawing of the row being added or edited.
pub fn view_window<'a, 'b>(
    scales: &'b [(String, String)],
    selected: &'b str,
    current: &'b str,
    name_buf: &'a str,
    paper_buf: &'a str,
    drawing_buf: &'a str,
) -> Element<'a, Message> {
    // ── Toolbar: New / Delete | Set Current / Apply ───────────────────────
    let toolbar = container(
        row![
            tb_button("New", Message::ScaleManagerNew, false),
            tb_button("Delete", Message::ScaleManagerDelete, false),
            Space::new().width(Fill),
            tb_button("Set Current", Message::ScaleManagerSetCurrent, false),
            tb_button("Apply", Message::ScaleManagerApply, true),
        ]
        .spacing(4)
        .align_y(iced::Center),
    )
    .style(|_: &Theme| container::Style {
        background: Some(Background::Color(TB)),
        ..Default::default()
    })
    .width(Fill)
    .padding([5, 8]);

    // ── Left: scale list ──────────────────────────────────────────────────
    let rows: Vec<Element<'_, Message>> = scales
        .iter()
        .map(|(name, ratio)| {
            let is_sel = name.as_str() == selected;
            let is_cur = name.eq_ignore_ascii_case(current);
            let check = crate::ui::icons::check_cell(is_cur, CURRENT_CHECK);
            let label = row![
                check,
                text(name.clone()).size(11).color(TEXT).width(Fill),
                text(ratio.clone()).size(10).color(DIM),
            ]
            .spacing(4)
            .align_y(iced::Center);
            button(label)
                .on_press(Message::ScaleManagerSelect(name.clone()))
                .style(move |_: &Theme, st| button::Style {
                    background: Some(Background::Color(if is_sel {
                        ACTIVE
                    } else if matches!(st, button::Status::Hovered) {
                        Color {
                            r: 0.20,
                            g: 0.20,
                            b: 0.20,
                            a: 1.0,
                        }
                    } else {
                        Color::TRANSPARENT
                    })),
                    text_color: TEXT,
                    ..Default::default()
                })
                .width(Fill)
                .padding([4, 8])
                .into()
        })
        .collect();

    let list_panel = container(
        column![
            text("Scales").size(10).color(DIM),
            container(scrollable(column(rows).spacing(1)).height(Fill))
                .style(|_: &Theme| container::Style {
                    background: Some(Background::Color(LIST)),
                    border: Border {
                        color: BORDER,
                        width: 1.0,
                        radius: 3.0.into()
                    },
                    ..Default::default()
                })
                .width(Fill)
                .height(Fill)
                .padding(2),
        ]
        .spacing(4)
        .height(Fill),
    )
    .width(190)
    .height(Fill)
    .padding(iced::Padding {
        top: 12.0,
        right: 8.0,
        bottom: 12.0,
        left: 12.0,
    });

    // ── Right: editor (name + paper:drawing) ──────────────────────────────
    let field = |label: &'static str, value: &str, on: fn(String) -> Message| {
        row![
            text(label).size(11).color(DIM).width(96),
            text_input("", value)
                .on_input(on)
                .style(field_style)
                .size(12)
                .padding([5, 8])
                .width(Fill),
        ]
        .align_y(iced::Center)
        .spacing(6)
    };

    let editor = container(
        column![
            text("Scale").size(10).color(DIM),
            field("Name", name_buf, Message::ScaleManagerNameBuf),
            field("Paper units", paper_buf, Message::ScaleManagerPaperBuf),
            field("Drawing units", drawing_buf, Message::ScaleManagerDrawingBuf),
            Space::new().height(6),
            text("Type the ratio in the fields, then New to add or Apply to update the selected scale.")
                .size(10)
                .color(DIM),
        ]
        .spacing(8),
    )
    .width(Fill)
    .height(Fill)
    .padding(12);

    let body = row![list_panel, vsep(), editor].height(Fill);

    container(column![toolbar, hdivider(), body])
        .style(|_: &Theme| container::Style {
            background: Some(Background::Color(BG)),
            ..Default::default()
        })
        .width(Fill)
        .height(Fill)
        .into()
}
