import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "../src/accordion";
import { Button } from "../src/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "../src/empty";
import { Item, ItemGroup } from "../src/item";
import { ToggleGroup, ToggleGroupItem } from "../src/toggle-group";

afterEach(cleanup);

describe("token-styled composition primitives", () => {
  it.each(["default", "outline", "segmented"] as const)(
    "keeps %s toggle selection and disabled behavior",
    (variant) => {
      render(
        <ToggleGroup
          type="multiple"
          variant={variant}
          size="sm"
          aria-label="显示方式"
        >
          <ToggleGroupItem value="table">表格</ToggleGroupItem>
          <ToggleGroupItem value="plot" disabled>
            图形
          </ToggleGroupItem>
        </ToggleGroup>,
      );
      const group = screen.getByRole("toolbar", { name: "显示方式" });
      const table = screen.getByRole("button", { name: "表格" });
      expect(group).toHaveAttribute("data-variant", variant);
      expect(table).toHaveAttribute("data-variant", variant);
      expect(table).toHaveAttribute("data-size", "sm");
      fireEvent.click(table);
      expect(table).toHaveAttribute("aria-pressed", "true");
      fireEvent.click(table);
      expect(table).toHaveAttribute("aria-pressed", "false");
      expect(screen.getByRole("button", { name: "图形" })).toBeDisabled();
    },
  );

  it("leaves list semantics with the consumer and preserves nested buttons", () => {
    const view = render(
      <ItemGroup>
        <Item>布局项</Item>
      </ItemGroup>,
    );
    expect(screen.queryByRole("list")).toBeNull();
    view.rerender(
      <ItemGroup role="list" aria-label="论文">
        <div role="listitem">
          <Item asChild>
            <Button>打开论文</Button>
          </Item>
        </div>
      </ItemGroup>,
    );
    const item = within(screen.getByRole("list", { name: "论文" })).getByRole(
      "listitem",
    );
    expect(
      within(item).getByRole("button", { name: "打开论文" }),
    ).toBeEnabled();
  });

  it("keeps accordion expansion semantics with the shared empty presentation", () => {
    render(
      <Accordion type="single" collapsible>
        <AccordionItem value="data">
          <AccordionTrigger>来源</AccordionTrigger>
          <AccordionContent>
            <Empty>
              <EmptyHeader>
                <EmptyTitle>暂无来源</EmptyTitle>
                <EmptyDescription>选择研究对象后开始获取。</EmptyDescription>
              </EmptyHeader>
            </Empty>
          </AccordionContent>
        </AccordionItem>
      </Accordion>,
    );
    const trigger = screen.getByRole("button", { name: "来源" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("暂无来源")).toBeVisible();
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});
