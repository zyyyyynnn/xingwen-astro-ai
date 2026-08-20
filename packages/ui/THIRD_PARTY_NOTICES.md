# Third-Party Notices

This file lists the third-party source components adopted into `@xingwen/ui`
and their license terms. See `component-sources.json` for the full provenance
catalog including adaptation details and production consumers.

---

## shadcn/ui

- **Repository**: https://github.com/shadcn-ui/ui
- **Revisions**: `shadcn-ui@0.9.4` (`729b9ec8cacfae0bc31958c1a8e425d0a21be54e`)
  and `shadcn-cli@4.16.2` (`efac5987074af84ece57c367c6dd83387b967022`)
- **Adopted components**: Alert, Alert Dialog, Button, Checkbox, Collapsible,
  Command, Dialog, Dropdown Menu, Field, Input, Popover, Radio Group, Scroll
  Area, Select, Sheet, Skeleton, Sonner, Tabs, Textarea

### MIT License

Copyright (c) 2023 shadcn

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

## react-resizable-panels

- **Repository**: https://github.com/bvaughn/react-resizable-panels
- **Revision**: `4.12.2` (`a1eeb7aefdb024bb5879a323218e0ac05f77f28e`)
- **Adopted runtime**: Group, Panel, Separator
- **License**: MIT

The package owns panel sizing, pointer and keyboard resizing, constraints, and
separator accessibility. Xingwen exposes only thin governed aliases from
`@xingwen/ui` and does not maintain a parallel resize engine.
