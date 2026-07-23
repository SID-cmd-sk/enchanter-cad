//! Command-alias editor — an in-canvas modal (Plan B) for adding, remapping and
//! removing command-line aliases (the `ocad.pgp` table). Opened by ALIASEDIT.
//! Rows are `(alias, command)`; edits are buffered in `alias_editor_rows` and
//! committed to the alias table when the dialog closes. Mirrors the editable-row
//! pattern of the attribute editor and plugin manager.

use crate::app::Message;
use iced::widget::{button, column, container, row, scrollable, text, text_input, Space};
use iced::{Background, Border, Color, Element, Fill, Length, Theme};

/// Which column of an alias row a text edit targets.
#[derive(Clone, Copy, Debug)]
pub enum AliasField {
    Alias,
    Command,
}

/// Right-hand lane reserved for the scrollbar so it never overlaps the ✕ column.
const GUTTER: f32 = 16.0;

const BG: Color = Color { r: 0.15, g: 0.15, b: 0.15, a: 1.0 };
const FIELD_BG: Color = Color { r: 0.12, g: 0.12, b: 0.12, a: 1.0 };
const BORDER: Color = Color { r: 0.35, g: 0.35, b: 0.35, a: 1.0 };
const DIM: Color = Color { r: 0.55, g: 0.55, b: 0.55, a: 1.0 };
const WHITE: Color = Color { r: 0.85, g: 0.85, b: 0.85, a: 1.0 };
const ADD_C: Color = Color { r: 0.20, g: 0.40, b: 0.62, a: 1.0 };

fn field_style(_: &Theme, _s: text_input::Status) -> text_input::Style {
    text_input::Style {
        background: Background::Color(FIELD_BG),
        border: Border { color: BORDER, width: 1.0, radius: 3.0.into() },
        icon: WHITE,
        placeholder: DIM,
        value: WHITE,
        selection: Color { r: 0.25, g: 0.40, b: 0.60, a: 1.0 },
    }
}

/// Build the alias editor content. `rows` is the live working buffer.
pub fn view_window(rows: &[(String, String)]) -> Element<'_, Message> {
    let title = text("Command Aliases").size(15).color(WHITE);
    let hint = text(
        "Type an alias and the command it runs (e.g. L → LINE). \
         Apply to save to ocad.pgp; closing discards unapplied edits.",
    )
    .size(11)
    .color(DIM);

    // Right gutter reserved so the scrollbar has its own lane and never sits on
    // top of the row delete (✕) buttons. Applied to both the header and the
    // scrollable rows so the columns stay aligned.
    let gutter = iced::Padding { top: 0.0, right: GUTTER, bottom: 0.0, left: 0.0 };

    let head = container(
        row![
            container(text("Alias").size(11).color(DIM)).width(Length::Fixed(120.0)),
            container(text("Command").size(11).color(DIM)).width(Fill),
            Space::new().width(Length::Fixed(30.0)),
        ]
        .spacing(8),
    )
    .padding(gutter);

    let mut list = column![].spacing(3);
    for (idx, (alias, cmd)) in rows.iter().enumerate() {
        let alias_box = text_input("alias", alias)
            .on_input(move |v| Message::AliasEditorInput { idx, field: AliasField::Alias, value: v })
            .style(field_style)
            .size(13)
            .padding([3, 6])
            .width(Length::Fixed(120.0));
        let cmd_box = text_input("command", cmd)
            .on_input(move |v| Message::AliasEditorInput { idx, field: AliasField::Command, value: v })
            .style(field_style)
            .size(13)
            .padding([3, 6])
            .width(Fill);
        let del = button(crate::ui::icons::tinted(crate::ui::icons::CLOSE, 12.0, WHITE))
            .on_press(Message::AliasEditorRemove(idx))
            .padding([2, 6])
            .style(|_: &Theme, status| {
                let bg = if matches!(status, button::Status::Hovered) {
                    Color { r: 0.45, g: 0.22, b: 0.22, a: 1.0 }
                } else {
                    Color { r: 0.22, g: 0.22, b: 0.22, a: 1.0 }
                };
                button::Style {
                    background: Some(Background::Color(bg)),
                    border: Border { color: BORDER, width: 1.0, radius: 3.0.into() },
                    ..Default::default()
                }
            });
        list = list.push(
            row![alias_box, cmd_box, del]
                .spacing(8)
                .align_y(iced::Center),
        );
    }

    let add = button(text("+ Add alias").size(12).color(WHITE))
        .on_press(Message::AliasEditorAdd)
        .padding([4, 10])
        .style(|_: &Theme, status| {
            let bg = if matches!(status, button::Status::Hovered) {
                Color { r: 0.30, g: 0.30, b: 0.30, a: 1.0 }
            } else {
                Color { r: 0.22, g: 0.22, b: 0.22, a: 1.0 }
            };
            button::Style {
                background: Some(Background::Color(bg)),
                text_color: WHITE,
                border: Border { color: BORDER, width: 1.0, radius: 3.0.into() },
                ..Default::default()
            }
        });

    // Apply — primary action; commits the rows to ocad.pgp and stays open.
    let apply = button(text("Apply").size(12).color(WHITE))
        .on_press(Message::AliasEditorApply)
        .padding([4, 16])
        .style(|_: &Theme, status| {
            let bg = if matches!(status, button::Status::Hovered | button::Status::Pressed) {
                Color { r: 0.24, g: 0.46, b: 0.74, a: 1.0 }
            } else {
                ADD_C
            };
            button::Style {
                background: Some(Background::Color(bg)),
                text_color: WHITE,
                border: Border { radius: 4.0.into(), ..Default::default() },
                ..Default::default()
            }
        });

    container(
        column![
            title,
            hint,
            Space::new().height(6),
            head,
            scrollable(container(list).padding(gutter)).height(Fill),
            Space::new().height(6),
            row![add, Space::new().width(Fill), apply].align_y(iced::Center),
        ]
        .spacing(6)
        .width(Fill)
        .height(Fill),
    )
    .padding(12)
    .width(Fill)
    .height(Fill)
    .style(|_: &Theme| container::Style {
        background: Some(Background::Color(BG)),
        ..Default::default()
    })
    .into()
}
