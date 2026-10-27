import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ParsedDataPreview from '../ParsedDataPreview';
import type { ParsedResume, ParsedVacancy } from '@/services/api';

const mockParsedResume: ParsedResume = {
  name: 'John Doe',
  email: 'john@example.com',
  phone: '+79991234567',
  telegram: '@johndoe',
  position: 'Python Developer',
  company: 'TechCorp',
  experience_years: 5,
  skills: ['Python', 'FastAPI', 'PostgreSQL'],
  salary_min: 200000,
  salary_max: 300000,
  salary_currency: 'RUB',
  location: 'Moscow',
  summary: 'Experienced backend developer',
  source_url: 'https://hh.ru/resume/123',
};

const mockParsedVacancy: ParsedVacancy = {
  title: 'Senior Python Developer',
  description: 'We are looking for an experienced developer',
  requirements: '5+ years Python experience',
  responsibilities: 'Develop backend services',
  salary_min: 250000,
  salary_max: 400000,
  salary_currency: 'RUB',
  location: 'Remote',
  employment_type: 'full-time',
  experience_level: 'senior',
  company_name: 'StartupXYZ',
  source_url: 'https://hh.ru/vacancy/456',
};

describe('ParsedDataPreview', () => {
  const mockOnDataChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Resume Preview', () => {
    const renderResumePreview = (data: ParsedResume = mockParsedResume) => {
      return render(
        <ParsedDataPreview
          type="resume"
          data={data}
          onDataChange={mockOnDataChange}
        />
      );
    };

    describe('Rendering', () => {
      it('should render parsed indicator', () => {
        renderResumePreview();
        expect(screen.getByText('Распознано:')).toBeInTheDocument();
      });

      it('should render all resume fields', () => {
        renderResumePreview();
        expect(screen.getByText('Имя')).toBeInTheDocument();
        expect(screen.getByText('Email')).toBeInTheDocument();
        expect(screen.getByText('Телефон')).toBeInTheDocument();
        expect(screen.getByText('Telegram')).toBeInTheDocument();
        expect(screen.getByText('Должность')).toBeInTheDocument();
        expect(screen.getByText('Компания')).toBeInTheDocument();
        expect(screen.getByText('Опыт (лет)')).toBeInTheDocument();
        expect(screen.getByText('Локация')).toBeInTheDocument();
        expect(screen.getByText('Зарплата от')).toBeInTheDocument();
        expect(screen.getByText('Зарплата до')).toBeInTheDocument();
        expect(screen.getByText('Валюта')).toBeInTheDocument();
        expect(screen.getByText('Навыки (через запятую)')).toBeInTheDocument();
        expect(screen.getByText('Описание')).toBeInTheDocument();
      });

      it('should display parsed resume data correctly', () => {
        renderResumePreview();
        // ФИО разложено по трём полям: Фамилия / Имя / Отчество.
        expect(screen.getByPlaceholderText('Фамилия')).toHaveValue('John');
        expect(screen.getByPlaceholderText('Имя')).toHaveValue('Doe');
        expect(screen.getByDisplayValue('john@example.com')).toBeInTheDocument();
        expect(screen.getByDisplayValue('+79991234567')).toBeInTheDocument();
        expect(screen.getByDisplayValue('@johndoe')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Python Developer')).toBeInTheDocument();
        expect(screen.getByDisplayValue('TechCorp')).toBeInTheDocument();
        expect(screen.getByDisplayValue('5')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Moscow')).toBeInTheDocument();
        expect(screen.getByDisplayValue('200000')).toBeInTheDocument();
        expect(screen.getByDisplayValue('300000')).toBeInTheDocument();
      });

      it('should display skills as comma-separated value', () => {
        renderResumePreview();
        expect(screen.getByDisplayValue('Python, FastAPI, PostgreSQL')).toBeInTheDocument();
      });

      it('should display skills as tags', () => {
        renderResumePreview();
        expect(screen.getByText('Python')).toBeInTheDocument();
        expect(screen.getByText('FastAPI')).toBeInTheDocument();
        expect(screen.getByText('PostgreSQL')).toBeInTheDocument();
      });

      it('should display summary in textarea', () => {
        renderResumePreview();
        expect(screen.getByDisplayValue('Experienced backend developer')).toBeInTheDocument();
      });
    });

    describe('Field Editing - Name', () => {
      it('should update name when typed', async () => {
        renderResumePreview();
        const lastNameInput = screen.getByPlaceholderText('Фамилия');
        const firstNameInput = screen.getByPlaceholderText('Имя');
        await userEvent.clear(lastNameInput);
        await userEvent.type(lastNameInput, 'Jane');
        await userEvent.clear(firstNameInput);
        await userEvent.type(firstNameInput, 'Smith');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.name).toBe('Jane Smith');
      });
    });

    describe('Field Editing - Email', () => {
      it('should update email when typed', async () => {
        renderResumePreview();
        const emailInput = screen.getByDisplayValue('john@example.com');
        await userEvent.clear(emailInput);
        await userEvent.type(emailInput, 'jane@example.com');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.email).toBe('jane@example.com');
      });
    });

    describe('Field Editing - Phone', () => {
      it('should update phone when typed', async () => {
        renderResumePreview();
        const phoneInput = screen.getByDisplayValue('+79991234567');
        await userEvent.clear(phoneInput);
        await userEvent.type(phoneInput, '+79999999999');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.phone).toBe('+79999999999');
      });
    });

    describe('Field Editing - Telegram', () => {
      it('should update telegram when typed', async () => {
        renderResumePreview();
        const telegramInput = screen.getByDisplayValue('@johndoe');
        await userEvent.clear(telegramInput);
        await userEvent.type(telegramInput, '@janesmith');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.telegram).toBe('@janesmith');
      });
    });

    describe('Field Editing - Position', () => {
      it('should update position when typed', async () => {
        renderResumePreview();
        const positionInput = screen.getByDisplayValue('Python Developer');
        await userEvent.clear(positionInput);
        await userEvent.type(positionInput, 'Senior Backend Engineer');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.position).toBe('Senior Backend Engineer');
      });
    });

    describe('Field Editing - Company', () => {
      it('should update company when typed', async () => {
        renderResumePreview();
        const companyInput = screen.getByDisplayValue('TechCorp');
        await userEvent.clear(companyInput);
        await userEvent.type(companyInput, 'NewCorp');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.company).toBe('NewCorp');
      });
    });

    describe('Field Editing - Experience Years', () => {
      it('should update experience years when typed', async () => {
        renderResumePreview();
        const experienceInput = screen.getByDisplayValue('5');
        await userEvent.clear(experienceInput);
        await userEvent.type(experienceInput, '10');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.experience_years).toBe(10);
      });

      it('should handle empty experience years', async () => {
        renderResumePreview();
        const experienceInput = screen.getByDisplayValue('5');
        await userEvent.clear(experienceInput);

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.experience_years).toBeUndefined();
      });
    });

    describe('Field Editing - Location', () => {
      it('should update location when typed', async () => {
        renderResumePreview();
        const locationInput = screen.getByDisplayValue('Moscow');
        await userEvent.clear(locationInput);
        await userEvent.type(locationInput, 'Saint Petersburg');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.location).toBe('Saint Petersburg');
      });
    });

    describe('Field Editing - Salary', () => {
      it('should update salary_min when typed', async () => {
        renderResumePreview();
        const salaryMinInput = screen.getByDisplayValue('200000');
        await userEvent.clear(salaryMinInput);
        await userEvent.type(salaryMinInput, '250000');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.salary_min).toBe(250000);
      });

      it('should update salary_max when typed', async () => {
        renderResumePreview();
        const salaryMaxInput = screen.getByDisplayValue('300000');
        await userEvent.clear(salaryMaxInput);
        await userEvent.type(salaryMaxInput, '400000');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.salary_max).toBe(400000);
      });

      it('should handle empty salary values', async () => {
        renderResumePreview();
        const salaryMinInput = screen.getByDisplayValue('200000');
        await userEvent.clear(salaryMinInput);

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.salary_min).toBeUndefined();
      });
    });

    describe('Currency Dropdown', () => {
      it('should display current currency', () => {
        renderResumePreview();
        const currencySelect = screen.getByRole('combobox') as HTMLSelectElement;
        expect(currencySelect.value).toBe('RUB');
      });

      it('should show only RUB and USD currency options', () => {
        renderResumePreview();
        const currencySelect = screen.getByRole('combobox');
        const options = currencySelect.querySelectorAll('option');
        // По требованию — только рубль и доллар.
        expect(options.length).toBe(2);
        expect((options[0] as HTMLOptionElement).value).toBe('RUB');
        expect(options[0].textContent).toContain('₽');
        expect((options[1] as HTMLOptionElement).value).toBe('USD');
        expect(options[1].textContent).toContain('$');
      });

      it('should update currency when changed', async () => {
        renderResumePreview();
        const currencySelect = screen.getByRole('combobox');
        await userEvent.selectOptions(currencySelect, 'USD');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.salary_currency).toBe('USD');
      });

      it('should default to RUB when currency is not set', () => {
        const resumeWithoutCurrency = { ...mockParsedResume, salary_currency: undefined } as ParsedResume;
        render(
          <ParsedDataPreview
            type="resume"
            data={resumeWithoutCurrency}
            onDataChange={mockOnDataChange}
          />
        );

        const currencySelect = screen.getByRole('combobox') as HTMLSelectElement;
        expect(currencySelect.value).toBe('RUB');
      });
    });

    describe('Field Editing - Skills', () => {
      it('should parse skills from comma-separated input', async () => {
        renderResumePreview();
        const skillsInput = screen.getByDisplayValue('Python, FastAPI, PostgreSQL');
        await userEvent.clear(skillsInput);
        await userEvent.type(skillsInput, 'JavaScript, React, Node.js');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.skills).toEqual(['JavaScript', 'React', 'Node.js']);
      });

      it('should handle skills with extra spaces', async () => {
        renderResumePreview();
        const skillsInput = screen.getByDisplayValue('Python, FastAPI, PostgreSQL');
        await userEvent.clear(skillsInput);
        await userEvent.type(skillsInput, '  Skill1  ,  Skill2  ,  Skill3  ');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.skills).toEqual(['Skill1', 'Skill2', 'Skill3']);
      });

      it('should filter out empty skills', async () => {
        renderResumePreview();
        const skillsInput = screen.getByDisplayValue('Python, FastAPI, PostgreSQL');
        await userEvent.clear(skillsInput);
        await userEvent.type(skillsInput, 'Skill1, , Skill2, , Skill3');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.skills).toEqual(['Skill1', 'Skill2', 'Skill3']);
      });

      it('should handle empty skills string', async () => {
        renderResumePreview();
        const skillsInput = screen.getByDisplayValue('Python, FastAPI, PostgreSQL');
        await userEvent.clear(skillsInput);

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.skills).toEqual([]);
      });
    });

    describe('Field Editing - Summary', () => {
      it('should update summary when typed', async () => {
        renderResumePreview();
        const summaryTextarea = screen.getByDisplayValue('Experienced backend developer');
        await userEvent.clear(summaryTextarea);
        await userEvent.type(summaryTextarea, 'New summary text');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.summary).toBe('New summary text');
      });
    });

    describe('Empty Fields', () => {
      it('should handle resume with missing optional fields', () => {
        const minimalResume: ParsedResume = {
          name: 'John Doe',
          skills: [],
          salary_currency: 'RUB',
        };

        render(
          <ParsedDataPreview
            type="resume"
            data={minimalResume}
            onDataChange={mockOnDataChange}
          />
        );

        expect(screen.getByPlaceholderText('Фамилия')).toHaveValue('John');
        // Empty fields should show empty inputs
        expect(screen.getByPlaceholderText('candidate@example.com')).toHaveValue('');
        expect(screen.getByPlaceholderText('+7 999 123-45-67')).toHaveValue('');
      });

      it('should handle empty skills array', () => {
        const resumeNoSkills: ParsedResume = {
          ...mockParsedResume,
          skills: [],
        };

        render(
          <ParsedDataPreview
            type="resume"
            data={resumeNoSkills}
            onDataChange={mockOnDataChange}
          />
        );

        const skillsInput = screen.getByPlaceholderText('Python, FastAPI, PostgreSQL');
        expect(skillsInput).toHaveValue('');
      });
    });

    describe('Data Synchronization', () => {
      it('should update local state when data prop changes', async () => {
        const { rerender } = renderResumePreview();

        // Verify initial data
        expect(screen.getByPlaceholderText('Фамилия')).toHaveValue('John');

        // Update data prop
        const updatedResume = { ...mockParsedResume, name: 'Updated Name' };
        rerender(
          <ParsedDataPreview
            type="resume"
            data={updatedResume}
            onDataChange={mockOnDataChange}
          />
        );

        // Verify updated data
        await waitFor(() => {
          expect(screen.getByPlaceholderText('Фамилия')).toHaveValue('Updated');
          expect(screen.getByPlaceholderText('Имя')).toHaveValue('Name');
        });
      });
    });
  });

  describe('Vacancy Preview', () => {
    const renderVacancyPreview = (data: ParsedVacancy = mockParsedVacancy) => {
      return render(
        <ParsedDataPreview
          type="vacancy"
          data={data}
          onDataChange={mockOnDataChange}
        />
      );
    };

    describe('Rendering', () => {
      it('should render parsed indicator', () => {
        renderVacancyPreview();
        expect(screen.getByText('Распознано:')).toBeInTheDocument();
      });

      it('should render all vacancy fields', () => {
        renderVacancyPreview();
        expect(screen.getByText('Название вакансии *')).toBeInTheDocument();
        expect(screen.getByText('Компания')).toBeInTheDocument();
        expect(screen.getByText('Локация')).toBeInTheDocument();
        expect(screen.getByText('Тип занятости')).toBeInTheDocument();
        expect(screen.getByText('Уровень')).toBeInTheDocument();
        expect(screen.getByText('Зарплата от')).toBeInTheDocument();
        expect(screen.getByText('Зарплата до')).toBeInTheDocument();
        expect(screen.getByText('Валюта')).toBeInTheDocument();
        expect(screen.getByText('Описание')).toBeInTheDocument();
        expect(screen.getByText('Требования')).toBeInTheDocument();
        expect(screen.getByText('Обязанности')).toBeInTheDocument();
      });

      it('should display parsed vacancy data correctly', () => {
        renderVacancyPreview();
        expect(screen.getByDisplayValue('Senior Python Developer')).toBeInTheDocument();
        expect(screen.getByDisplayValue('StartupXYZ')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Remote')).toBeInTheDocument();
        expect(screen.getByDisplayValue('250000')).toBeInTheDocument();
        expect(screen.getByDisplayValue('400000')).toBeInTheDocument();
      });
    });

    describe('Field Editing - Title', () => {
      it('should update title when typed', async () => {
        renderVacancyPreview();
        const titleInput = screen.getByDisplayValue('Senior Python Developer');
        await userEvent.clear(titleInput);
        await userEvent.type(titleInput, 'Lead Backend Developer');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.title).toBe('Lead Backend Developer');
      });
    });

    describe('Field Editing - Company Name', () => {
      it('should update company_name when typed', async () => {
        renderVacancyPreview();
        const companyInput = screen.getByDisplayValue('StartupXYZ');
        await userEvent.clear(companyInput);
        await userEvent.type(companyInput, 'NewCompany');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.company_name).toBe('NewCompany');
      });
    });

    describe('Field Editing - Location', () => {
      it('should update location when typed', async () => {
        renderVacancyPreview();
        const locationInput = screen.getByDisplayValue('Remote');
        await userEvent.clear(locationInput);
        await userEvent.type(locationInput, 'Hybrid / Moscow');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.location).toBe('Hybrid / Moscow');
      });
    });

    describe('Employment Type Dropdown', () => {
      it('should display current employment type', () => {
        renderVacancyPreview();
        const selects = screen.getAllByRole('combobox');
        const employmentSelect = selects.find(
          (select) => (select as HTMLSelectElement).value === 'full-time'
        ) as HTMLSelectElement;
        expect(employmentSelect).toBeInTheDocument();
      });

      it('should show all employment type options', () => {
        renderVacancyPreview();
        expect(screen.getByText('Полная занятость')).toBeInTheDocument();
        expect(screen.getByText('Частичная занятость')).toBeInTheDocument();
        expect(screen.getByText('Контракт')).toBeInTheDocument();
        expect(screen.getByText('Удалённая работа')).toBeInTheDocument();
        expect(screen.getByText('Гибрид')).toBeInTheDocument();
      });

      it('should update employment_type when changed', async () => {
        renderVacancyPreview();
        const selects = screen.getAllByRole('combobox');
        const employmentSelect = selects.find(
          (select) => (select as HTMLSelectElement).value === 'full-time'
        );
        if (employmentSelect) {
          await userEvent.selectOptions(employmentSelect, 'remote');

          expect(mockOnDataChange).toHaveBeenCalled();
          const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
          expect(lastCall.employment_type).toBe('remote');
        }
      });
    });

    describe('Experience Level Dropdown', () => {
      it('should display current experience level', () => {
        renderVacancyPreview();
        const selects = screen.getAllByRole('combobox');
        const levelSelect = selects.find(
          (select) => (select as HTMLSelectElement).value === 'senior'
        ) as HTMLSelectElement;
        expect(levelSelect).toBeInTheDocument();
      });

      it('should show all experience level options', () => {
        renderVacancyPreview();
        expect(screen.getByText('Стажёр')).toBeInTheDocument();
        expect(screen.getByText('Junior')).toBeInTheDocument();
        expect(screen.getByText('Middle')).toBeInTheDocument();
        expect(screen.getByText('Senior')).toBeInTheDocument();
        expect(screen.getByText('Lead')).toBeInTheDocument();
        expect(screen.getByText('Manager')).toBeInTheDocument();
      });

      it('should update experience_level when changed', async () => {
        renderVacancyPreview();
        const selects = screen.getAllByRole('combobox');
        const levelSelect = selects.find(
          (select) => (select as HTMLSelectElement).value === 'senior'
        );
        if (levelSelect) {
          await userEvent.selectOptions(levelSelect, 'lead');

          expect(mockOnDataChange).toHaveBeenCalled();
          const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
          expect(lastCall.experience_level).toBe('lead');
        }
      });
    });

    describe('Currency Dropdown for Vacancy', () => {
      it('should display current currency', () => {
        renderVacancyPreview();
        const selects = screen.getAllByRole('combobox');
        // Валютный select — тот, где среди опций есть символ рубля.
        const currencySelect = selects.find(
          (select) => {
            const options = select.querySelectorAll('option');
            return Array.from(options).some(opt => opt.textContent?.includes('₽'));
          }
        );
        expect(currencySelect).toBeInTheDocument();
      });

      it('should update salary_currency when changed', async () => {
        renderVacancyPreview();
        const selects = screen.getAllByRole('combobox');
        // Валютный select — тот, где среди опций есть символ рубля.
        const currencySelect = selects.find(
          (select) => {
            const options = select.querySelectorAll('option');
            return Array.from(options).some(opt => opt.textContent?.includes('₽'));
          }
        );
        if (currencySelect) {
          await userEvent.selectOptions(currencySelect, 'USD');

          expect(mockOnDataChange).toHaveBeenCalled();
          const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
          expect(lastCall.salary_currency).toBe('USD');
        }
      });
    });

    describe('Field Editing - Description', () => {
      it('should update description when typed', async () => {
        renderVacancyPreview();
        const descInput = screen.getByDisplayValue('We are looking for an experienced developer');
        await userEvent.clear(descInput);
        await userEvent.type(descInput, 'New job description');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.description).toBe('New job description');
      });
    });

    describe('Field Editing - Requirements', () => {
      it('should update requirements when typed', async () => {
        renderVacancyPreview();
        const reqInput = screen.getByDisplayValue('5+ years Python experience');
        await userEvent.clear(reqInput);
        await userEvent.type(reqInput, 'New requirements');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.requirements).toBe('New requirements');
      });
    });

    describe('Field Editing - Responsibilities', () => {
      it('should update responsibilities when typed', async () => {
        renderVacancyPreview();
        const respInput = screen.getByDisplayValue('Develop backend services');
        await userEvent.clear(respInput);
        await userEvent.type(respInput, 'New responsibilities');

        expect(mockOnDataChange).toHaveBeenCalled();
        const lastCall = mockOnDataChange.mock.calls[mockOnDataChange.mock.calls.length - 1][0];
        expect(lastCall.responsibilities).toBe('New responsibilities');
      });
    });

    describe('Validation - Required Fields', () => {
      it('should show error indicator when title is empty', () => {
        const vacancyWithoutTitle = { ...mockParsedVacancy, title: '' };
        render(
          <ParsedDataPreview
            type="vacancy"
            data={vacancyWithoutTitle}
            onDataChange={mockOnDataChange}
          />
        );

        expect(screen.getByText('Название обязательно')).toBeInTheDocument();
      });

      it('should show red border when title is empty', () => {
        const vacancyWithoutTitle = { ...mockParsedVacancy, title: '' };
        render(
          <ParsedDataPreview
            type="vacancy"
            data={vacancyWithoutTitle}
            onDataChange={mockOnDataChange}
          />
        );

        const titleInput = screen.getByPlaceholderText('Senior Python Developer');
        expect(titleInput.classList.toString()).toContain('hf-status-red');
      });

      it('should not show error when title is provided', () => {
        renderVacancyPreview();
        expect(screen.queryByText('Название обязательно')).not.toBeInTheDocument();
      });
    });

    describe('Empty Fields', () => {
      it('should handle vacancy with missing optional fields', () => {
        const minimalVacancy: ParsedVacancy = {
          title: 'Basic Vacancy',
          salary_currency: 'RUB',
        };

        render(
          <ParsedDataPreview
            type="vacancy"
            data={minimalVacancy}
            onDataChange={mockOnDataChange}
          />
        );

        expect(screen.getByDisplayValue('Basic Vacancy')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('ООО Компания')).toHaveValue('');
      });
    });
  });
});
