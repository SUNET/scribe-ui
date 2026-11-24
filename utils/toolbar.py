# Copyright (c) 2025-2026 Sunet.
# Contributor: Kristofer Hallin
#
# This file is part of Sunet Scribe.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A toolbar the keyboard moves through the way the ARIA Authoring Practices
describe one: a single Tab stop, the arrow keys between its buttons.

Without it every button of the editor's toolbar was a Tab stop of its own,
and getting from the top of the page to the text took a press for each. With
it, Tab goes into the bar -- to its first button from the left that is not
greyed out, from either side and whatever was used last -- and the next Tab
goes on past it; Left and Right move between the buttons, wrapping round,
and Home and End go to the first and the last. A screen reader says
"toolbar" and its name on the way in, which is what tells the reader the
arrows work there (role=toolbar promises it).

The buttons' own tabindex is left alone. Quasar sets it on every q-btn and
sets it again whenever a button changes (Undo being enabled, say), so a
roving tabindex would be undone under it; the keys are taken instead, at the
document, for any element with role=toolbar and data-roving. Nothing changes
for the mouse, or on the screen.
"""

from nicegui import ui

KEYS = """<script>
(() => {
  if (window.scribeToolbarKeys) return;
  window.scribeToolbarKeys = true;

  const BAR = '[role="toolbar"][data-roving]';
  const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex], [contenteditable="true"]';

  // What Tab could land on: in the tab order, not disabled, on the screen.
  const usable = (el) =>
    (el.isContentEditable && el.getAttribute('contenteditable') === 'true' ? true : el.tabIndex >= 0) &&
    !el.disabled &&
    el.getClientRects().length > 0;

  const itemsOf = (bar) => [...bar.querySelectorAll(FOCUSABLE)].filter(usable);

  // The button focus is in. A click gives focus to a span inside Quasar's
  // button rather than to the button, and the arrows should still work.
  const itemOf = (items, target) => items.find((el) => el === target || el.contains(target));
  let byTab = false;

  document.addEventListener('keydown', (event) => { byTab = event.key === 'Tab'; }, true);
  document.addEventListener('mousedown', () => { byTab = false; }, true);

  // Into the bar with Tab or Shift+Tab, from outside it: to its first
  // button that can be used -- the first from the left that is not greyed
  // out -- whichever side it is entered from, and whichever button was used
  // last. The same place every time, as the toolbar pattern has it, rather
  // than one that depends on what was clicked earlier. Focus put on a
  // button any other way (a click, or a card closing and handing focus
  // back to the button that opened it) is left where it is.
  document.addEventListener('focusin', (event) => {
    const bar = event.target.closest && event.target.closest(BAR);
    if (!bar || !byTab) return;

    const from = event.relatedTarget;
    if (from && bar.contains(from)) return;

    const first = itemsOf(bar)[0];
    if (first && first !== event.target && !first.contains(event.target)) first.focus();
  });

  document.addEventListener('keydown', (event) => {
    const bar = event.target.closest && event.target.closest(BAR);
    if (!bar || event.ctrlKey || event.metaKey || event.altKey) return;

    const items = itemsOf(bar);
    const at = items.indexOf(itemOf(items, event.target));
    if (at < 0) return;

    let to = null;

    if (event.key === 'ArrowRight') to = items[(at + 1) % items.length];
    else if (event.key === 'ArrowLeft') to = items[(at - 1 + items.length) % items.length];
    else if (event.key === 'Home') to = items[0];
    else if (event.key === 'End') to = items[items.length - 1];
    else if (event.key === 'Tab') {
      // On past the bar, as from a single stop: the first thing after it,
      // or with Shift the last thing before it.
      const outside = [...document.querySelectorAll(FOCUSABLE)].filter((el) => usable(el) && !bar.contains(el));
      const after = (el) => bar.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING;
      to = event.shiftKey ? outside.filter((el) => !after(el)).pop() : outside.find(after);
      if (!to) return;
    }

    if (!to) return;

    event.preventDefault();
    to.focus();
  });
})();
</script>"""


def roving_toolbar(element: ui.element, name: str) -> ui.element:
    """
    Make an element a toolbar named `name` that the keyboard moves through
    with the arrows (see above). The page gets the keys once, however many
    toolbars it has.
    """

    element.props("role=toolbar data-roving")
    # As a value, never formatted into props(): see set_attribute() in
    # utils/drive_dialogs.py.
    element._props["aria-label"] = name
    ui.add_body_html(KEYS)

    return element
