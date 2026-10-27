import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AddToVacancyModal from "../AddToVacancyModal";
import * as api from "@/services/api";
import type { Vacancy } from "@/types";

// Mock dependencies
vi.mock("@/services/api", () => ({
  getAllVacancies: vi.fn(),
  getEntityVacancies: vi.fn().mockResolvedValue([]),
  createApplication: vi.fn(),
}));

vi.mock("@/stores/authStore", () => ({
  useAuthStore: () => ({
    user: { id: 1, role: "superadmin", org_role: "owner" },
  }),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("framer-motion", () => ({
  motion: {
    div: ({
      children,
      onClick,
      className,
      ...props
    }: React.PropsWithChildren<Record<string, unknown>>) => (
      <div
        onClick={onClick as React.MouseEventHandler}
        className={className as string}
        {...props}
      >
        {children}
      </div>
    ),
  },
  AnimatePresence: ({ children }: React.PropsWithChildren<object>) => (
    <>{children}</>
  ),
}));

const mockVacancies: Vacancy[] = [
  {
    id: 1,
    title: "Senior Python Developer",
    description: "Backend development",
    status: "open",
    salary_min: 150000,
    salary_max: 250000,
    salary_currency: "RUB",
    location: "Moscow",
    employment_type: "full-time",
    experience_level: "senior",
    priority: 1,
    tags: ["python", "fastapi"],
    extra_data: {},
    applications_count: 5,
    stage_counts: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    department_name: "Engineering",
  },
  {
    id: 2,
    title: "Frontend Developer",
    description: "React development",
    status: "open",
    salary_min: 100000,
    salary_max: 180000,
    salary_currency: "RUB",
    location: "Remote",
    employment_type: "full-time",
    experience_level: "middle",
    priority: 2,
    tags: ["react", "typescript"],
    extra_data: {},
    applications_count: 3,
    stage_counts: {},
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

describe("AddToVacancyModal", () => {
  const mockOnClose = vi.fn();
  const mockOnSuccess = vi.fn();

  const defaultProps = {
    entityId: 1,
    entityName: "John Doe",
    onClose: mockOnClose,
    onSuccess: mockOnSuccess,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (api.getAllVacancies as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockVacancies,
    );
  });

  describe("Modal Open/Close", () => {
    it("should render Huntflow-style popover header", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      expect(screen.getByText(/подразделение: все/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/поиск/i)).toBeInTheDocument();
    });

    it("should close modal when Cancel button is clicked", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
      });

      const vacancyButton = screen
        .getByText("Senior Python Developer")
        .closest("button");
      if (vacancyButton) {
        await userEvent.click(vacancyButton);
      }

      const cancelButton = screen.getByText(/отмена/i);
      await userEvent.click(cancelButton);

      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  describe("Vacancy Loading", () => {
    it("should load vacancies on mount", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(api.getAllVacancies).toHaveBeenCalledWith({
          status: "open",
          search: undefined,
        });
      });
    });

    it("should display loading spinner while loading", async () => {
      // Delay the response to show loading state
      let resolvePromise: (value: Vacancy[]) => void;
      (api.getAllVacancies as ReturnType<typeof vi.fn>).mockImplementation(
        () =>
          new Promise((resolve) => {
            resolvePromise = resolve;
          }),
      );

      render(<AddToVacancyModal {...defaultProps} />);

      // Check for spinner (animate-spin class). Модалка теперь в портале на
      // document.body, поэтому ищем там, а не в container рендера.
      await waitFor(() => {
        const spinner = document.body.querySelector(".animate-spin");
        expect(spinner).toBeInTheDocument();
      });

      // Cleanup: resolve the promise to prevent test leakage
      resolvePromise!(mockVacancies);
    });

    it("should display vacancies after loading", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
        expect(screen.getByText("Frontend Developer")).toBeInTheDocument();
      });
    });

    it("should display vacancy department in Huntflow-style row", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Engineering")).toBeInTheDocument();
      });
    });

    it("should display department name when available", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Engineering")).toBeInTheDocument();
      });
    });

    it("should hide card-only application count in Huntflow-style row", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
      });
      expect(screen.queryByText(/5 кандидатов/i)).not.toBeInTheDocument();
    });
  });

  describe("Vacancy Selection", () => {
    it("should allow selecting a vacancy", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
      });

      const vacancyButton = screen
        .getByText("Senior Python Developer")
        .closest("button");
      if (vacancyButton) {
        await userEvent.click(vacancyButton);

        expect(vacancyButton.className).toContain("bg-[var(--hf-ui-selected)]");
      }
    });

    it("should allow changing selected vacancy", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
      });

      // Select first vacancy
      const firstVacancy = screen
        .getByText("Senior Python Developer")
        .closest("button");
      if (firstVacancy) {
        await userEvent.click(firstVacancy);
        expect(firstVacancy.className).toContain("bg-[var(--hf-ui-selected)]");
      }

      // Select second vacancy
      const secondVacancy = screen
        .getByText("Frontend Developer")
        .closest("button");
      if (secondVacancy) {
        await userEvent.click(secondVacancy);
        expect(secondVacancy.className).toContain("bg-[var(--hf-ui-selected)]");
        // First vacancy should no longer be selected
        if (firstVacancy) {
          expect(firstVacancy.className).not.toContain("bg-[var(--hf-ui-selected)]");
        }
      }
    });
  });

  describe("Search Functionality", () => {
    it("should have search input", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      const searchInput = screen.getByPlaceholderText(/поиск/i);
      expect(searchInput).toBeInTheDocument();
    });

    it("should filter vacancies when searching (client-side)", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      // Обе вакансии видны изначально (грузятся одним getAllVacancies, фильтр —
      // на клиенте по title/location/department, не серверный re-fetch).
      await screen.findByText("Senior Python Developer");
      expect(screen.getByText("Frontend Developer")).toBeInTheDocument();

      const searchInput = screen.getByPlaceholderText(/поиск/i);
      await userEvent.type(searchInput, "Python");

      await waitFor(
        () => {
          expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
          expect(screen.queryByText("Frontend Developer")).not.toBeInTheDocument();
        },
        { timeout: 800 },
      );
    });
  });

  describe("Source Selection", () => {
    it("should not render the legacy source dropdown in the Huntflow popover", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      expect(screen.queryByText(/источник/i)).not.toBeInTheDocument();
      expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    });
  });

  describe("Submit Application", () => {
    it("should hide submit button when no vacancy selected", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      expect(
        screen.queryByRole("button", { name: /добавить$/i }),
      ).not.toBeInTheDocument();
    });

    it("should enable submit button when vacancy is selected", async () => {
      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
      });

      const vacancyButton = screen
        .getByText("Senior Python Developer")
        .closest("button");
      if (vacancyButton) {
        await userEvent.click(vacancyButton);
      }

      const submitButton = screen.getByRole("button", { name: /добавить$/i });
      expect(submitButton).not.toBeDisabled();
    });

    it("should submit application and call onSuccess", async () => {
      (api.createApplication as ReturnType<typeof vi.fn>).mockResolvedValue({
        id: 1,
        entity_id: 1,
        vacancy_id: 1,
        stage: "applied",
      });

      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
      });

      // Select vacancy
      const vacancyButton = screen
        .getByText("Senior Python Developer")
        .closest("button");
      if (vacancyButton) {
        await userEvent.click(vacancyButton);
      }

      // Submit
      const submitButton = screen.getByRole("button", { name: /добавить$/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(api.createApplication).toHaveBeenCalledWith(1, {
          vacancy_id: 1,
          entity_id: 1,
          source: "manual_add",
        });
        expect(mockOnSuccess).toHaveBeenCalled();
      });
    });

    it("should show loading state during submission", async () => {
      (api.createApplication as ReturnType<typeof vi.fn>).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({}), 100)),
      );

      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
      });

      const vacancyButton = screen
        .getByText("Senior Python Developer")
        .closest("button");
      if (vacancyButton) {
        await userEvent.click(vacancyButton);
      }

      const submitButton = screen.getByRole("button", { name: /добавить$/i });
      await userEvent.click(submitButton);

      // Button should show "Dobavlenie..." (Adding...) while loading
      expect(screen.getByText(/добавление/i)).toBeInTheDocument();
    });
  });

  describe("Error Handling", () => {
    it("should handle API error when loading vacancies", async () => {
      const consoleError = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      (api.getAllVacancies as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error("API Error"),
      );

      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(consoleError).toHaveBeenCalled();
      });

      consoleError.mockRestore();
    });

    it("should handle API error when submitting", async () => {
      const toast = await import("react-hot-toast");
      (api.createApplication as ReturnType<typeof vi.fn>).mockRejectedValue({
        response: {
          data: { detail: "Entity already applied to this vacancy" },
        },
      });

      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        expect(screen.getByText("Senior Python Developer")).toBeInTheDocument();
      });

      const vacancyButton = screen
        .getByText("Senior Python Developer")
        .closest("button");
      if (vacancyButton) {
        await userEvent.click(vacancyButton);
      }

      const submitButton = screen.getByRole("button", { name: /добавить$/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        // Конфликт «уже в вакансии» теперь показывается именным тостом, а батч
        // не срывается (остальных это не блокирует).
        expect(toast.default.error).toHaveBeenCalledWith(
          "Кандидат John Doe уже есть в вакансии",
        );
      });
    });
  });

  describe("Empty State", () => {
    it("should show empty state when no vacancies available", async () => {
      (api.getAllVacancies as ReturnType<typeof vi.fn>).mockResolvedValue([]);

      render(<AddToVacancyModal {...defaultProps} />);

      await waitFor(() => {
        // Russian text: "Vakansii ne naydeny" (Vacancies not found)
        expect(screen.getByText(/вакансии не найдены/i)).toBeInTheDocument();
        // Russian text: "Net otkrytykh vakansiy" (No open vacancies)
        expect(screen.getByText(/нет открытых вакансий/i)).toBeInTheDocument();
      });
    });
  });
});
