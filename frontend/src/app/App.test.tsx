import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import App from "./App";

test("apresenta a fundação técnica do ObraControl no conteúdo principal", () => {
  render(<App />);

  const main = screen.getByRole("main");

  expect(
    within(main).getByRole("heading", { name: "ObraControl", level: 1 }),
  ).toBeVisible();
  expect(within(main).getByText("Fundação técnica do frontend.")).toBeVisible();
});
