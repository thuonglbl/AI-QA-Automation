import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SarahInputsForm, type SarahInputsRequest } from "../SarahInputsForm";

const bothNeeded: SarahInputsRequest = {
  needsUrl: true,
  needsChrome: true,
  chromeOnFile: false,
  chromeExample: "C:\\chrome.exe",
  cdpExample: "http://localhost:9222",
  environments: [],
};

describe("SarahInputsForm", () => {
  it("submits the entered URL and Chrome path (launch mode)", () => {
    const onSubmit = vi.fn();
    render(<SarahInputsForm request={bothNeeded} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByTestId("sarah-target-url"), {
      target: { value: "https://app.test/page" },
    });
    fireEvent.change(screen.getByTestId("sarah-chrome-path"), {
      target: { value: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" },
    });
    fireEvent.click(screen.getByTestId("sarah-inputs-submit"));

    expect(onSubmit).toHaveBeenCalledWith(
      "https://app.test/page",
      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "",
    );
  });

  it("accepts a CDP URL as the browser source for SSO reuse (no Chrome path)", () => {
    const onSubmit = vi.fn();
    render(<SarahInputsForm request={bothNeeded} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByTestId("sarah-target-url"), {
      target: { value: "https://app.test/secure" },
    });
    fireEvent.change(screen.getByTestId("sarah-cdp-url"), {
      target: { value: "http://localhost:9222" },
    });
    // Chrome path left empty — the CDP URL satisfies the browser-source requirement.
    fireEvent.click(screen.getByTestId("sarah-inputs-submit"));

    expect(onSubmit).toHaveBeenCalledWith("https://app.test/secure", "", "http://localhost:9222");
  });

  it("disables submit until a valid http URL and a browser source are present", () => {
    const onSubmit = vi.fn();
    render(<SarahInputsForm request={bothNeeded} onSubmit={onSubmit} />);

    const submit = screen.getByTestId("sarah-inputs-submit");
    fireEvent.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();

    // Non-http URL is rejected even with a Chrome path.
    fireEvent.change(screen.getByTestId("sarah-target-url"), {
      target: { value: "app.test" },
    });
    fireEvent.change(screen.getByTestId("sarah-chrome-path"), {
      target: { value: "C:\\chrome.exe" },
    });
    fireEvent.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("hides the Chrome field and shows the on-file note when chrome is saved", () => {
    const onSubmit = vi.fn();
    render(
      <SarahInputsForm
        request={{
          needsUrl: true,
          needsChrome: false,
          chromeOnFile: true,
          chromeExample: "",
          cdpExample: "http://localhost:9222",
          environments: [],
        }}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.queryByTestId("sarah-chrome-path")).not.toBeInTheDocument();
    expect(screen.getByTestId("sarah-chrome-on-file")).toBeInTheDocument();

    fireEvent.change(screen.getByTestId("sarah-target-url"), {
      target: { value: "https://app.test" },
    });
    fireEvent.click(screen.getByTestId("sarah-inputs-submit"));
    expect(onSubmit).toHaveBeenCalledWith("https://app.test", "", "");
  });

  it("offers an environment dropdown (not a URL field) and submits the chosen env's URL", () => {
    const onSubmit = vi.fn();
    render(
      <SarahInputsForm
        request={{
          needsUrl: true,
          needsChrome: false,
          chromeOnFile: true,
          chromeExample: "",
          cdpExample: "http://localhost:9222",
          environments: [
            { name: "Test 1", url: "https://test1.app" },
            { name: "Production", url: "https://app.example.com" },
          ],
        }}
        onSubmit={onSubmit}
      />,
    );

    // The free-text URL field is replaced by the environment selector.
    expect(screen.queryByTestId("sarah-target-url")).not.toBeInTheDocument();
    const select = screen.getByTestId("sarah-environment");

    // Cannot submit until an environment is chosen.
    fireEvent.click(screen.getByTestId("sarah-inputs-submit"));
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(select, { target: { value: "https://app.example.com" } });
    fireEvent.click(screen.getByTestId("sarah-inputs-submit"));
    expect(onSubmit).toHaveBeenCalledWith("https://app.example.com", "", "");
  });
});
