export interface ResearchOption {
  readonly value: string;
  readonly label: string;
  readonly description: string;
}

export function optionLabel(
  options: readonly ResearchOption[],
  value: string,
): string {
  return options.find((option) => option.value === value)?.label ?? "暂未命名";
}
