import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ReactElement } from "react";
import { render } from "@testing-library/react";
import { ActiveDomainProvider } from "../context/ActiveDomainContext";
import { ThemeProvider } from "../theme";

export function renderWithProviders(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  window.localStorage.setItem("hydra_domain", "prod");
  window.localStorage.setItem("hydra_token_map", JSON.stringify({ prod: "token" }));

  return render(
    <QueryClientProvider client={queryClient}>
      <ActiveDomainProvider>
        <ThemeProvider isDarkMode={false}>
          <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
        </ThemeProvider>
      </ActiveDomainProvider>
    </QueryClientProvider>,
  );
}
